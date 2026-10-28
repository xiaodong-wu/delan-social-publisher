"""Offline regression checks. Fake platform evidence is confined to temporary test directories."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from common import TARGET_URL, now, read_json, validate_permalink, write_json
from optimize_image import strip_metadata, encode_webp, create_transport_jpeg, validate, validate_transport
from publication_history import build_history, check_history, check_copy_novelty, product_key, post_key, local_records
from scrape_product import CandidateError, discover, extract, normalize_url, prepare_run, retry, select
from update_manifest import update
from validate_campaign import inspect_campaign, validate_copy
from validate_completion import complete
from record_reporting import HEADERS, SPREADSHEET_ID, plan, record

URL = 'https://en.delancable.com/product/36225'
POST = 'https://www.facebook.com/dlflexdelancable/posts/test-post'
RAW = b'''<meta name="description" content="Generic company warranty"><h1 class="xmdsite-item-title">Signal Cable</h1>
<figure class="xmdsite-head-cover"><img src="https://static.dcodingmax.com/hero.png"></figure>
<article class="xmdsite-article"><p>Certifications:</p><img src="badges.png">
<p><strong>Conductor:</strong> Stranded bare copper</p><p>Insulation: HDPE</p>
<p>Shield: Tinned copper braid</p><p>Jacket: TPU, TPE optional</p></article>
<footer><p>Twenty year warranty</p></footer>'''
COPY = '''🔌 Stranded bare copper conductors provide the construction described on this signal cable product page.
🛡 Tinned copper braid is the stated shield construction for this cable.
⚙ HDPE insulation is specified for the selected signal cable construction.
✅ TPU jacket construction is listed, with TPE optional for this product.

For buyers reviewing signal cable options, these published construction details offer a starting point for a technical discussion. Check the required installation conditions against the selected product specification before making a procurement decision.

Contact Delan Cable with your application requirements and request confirmation of the appropriate cable configuration.

''' + URL + '''
#DLFLEX #DelanCable #SignalCable #CableSourcing #Copper #Insulation #Shielding #CableSelection'''


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def campaign(self, mode='live'):
        product = extract(RAW, URL)
        image = Image.new('RGB', (1024, 1024), '#334455')
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        ledger = self.root / 'selection/ledger.json'
        manifest = prepare_run(self.root, product, RAW, buf.getvalue(), 'png', ledger, mode)
        m = read_json(manifest); m['version'] = 1; write_json(manifest, m)
        root = manifest.parent
        (root / 'facebook.txt').write_text(COPY)
        (root / 'generated-social.png').write_bytes(buf.getvalue())
        (root / 'social.webp').write_bytes(encode_webp(strip_metadata(image), 88))
        create_transport_jpeg(strip_metadata(image), root / 'social-upload.jpg')
        write_json(root / 'evidence/product-review.json', {'status':'approved','reviewed_at':now(), 'notes':'Synthetic offline fixture', 'usable_fact_ids':['f01','f02','f03','f04'], 'conflicts':[]})
        write_json(root / 'evidence/copy-review.json', {'status':'approved','reviewed_at':now(), 'notes':'Synthetic fixture', 'all_claims_checked':True, 'claims':[
            {'text':'Stranded bare copper','fact_ids':['f01']}, {'text':'Tinned copper braid','fact_ids':['f03']},
            {'text':'HDPE insulation','fact_ids':['f02']}, {'text':'TPU jacket','fact_ids':['f04']}]})
        write_json(root / 'evidence/image-review.json', {'status':'approved','reviewed_at':now(), 'notes':'Synthetic fixture, not a real image review', 'source':'source/hero.png','final':'social.webp','panels':4,'material_issues':[], 'attempt_count':1,'versions':[{'path':'generated-social.png','outcome':'accepted'}]})
        (root / 'evidence/test-observation.txt').write_text('Offline simulated observation; no platform was contacted.')
        write_json(root / 'evidence/preflight.json', {'target_url':TARGET_URL, 'checked_at':now(), 'identity_confirmed':True,'can_create_post':True,'active_identity':'Fixture Delan', 'observed_page_id':'123456789','evidence_file':'evidence/test-observation.txt', 'ai_label':{'value':'off','reason':'Synthetic optional-off UI observation'}})
        snapshot = build_history(self.root)
        snapshot.update(coverage='local_and_sheet', sheet_checked_at=now())
        write_json(root / 'evidence/history-preflight.json', snapshot)
        report = inspect_campaign(manifest)
        write_json(root / 'evidence/campaign-validation.json', report)
        write_json(ledger, {'targeted':False,'status':'selected','attempts':[{'url':URL,'status':'selected','manifest':str(manifest)}]})
        return manifest

    def publication(self, manifest):
        evidence = manifest.parent / 'evidence/facebook-publication.json'
        write_json(evidence, {'target_url':TARGET_URL,'post_url':POST,'verified_at':now(),'author_matches':True,'text_matches':True,'product_link_matches':True,'image_matches':True,'evidence_file':'evidence/test-observation.txt','notes':'Offline fixture only'})
        return evidence

    def reporting(self, manifest, change=None):
        values = plan(manifest)['values']
        cells = lambda row: {'values': [{'userEnteredValue': {'stringValue': v}} for v in row]}
        evidence = {'verified_at': now(), 'row_number': 2,
                    'readback': {'spreadsheetId': SPREADSHEET_ID, 'properties': {'title': 'social-auto-upload'},
                                 'sheets': [{'properties': {'sheetId': 0, 'title': '工作表1', 'gridProperties': {'rowCount': 1000}},
                                             'data': [{'rowData': [cells(HEADERS), cells(values)]}]}]},
                    'search': {'matched_row_count': 1, 'returned_matching_row_count': 1,
                               'scanned_range': 'A1:E1000', 'truncated': False,
                               'markdown': '| 2 | ' + ' | '.join(values) + ' |'}}
        if change:
            change(evidence)
        path = manifest.parent / 'evidence/google-sheet-verification.json'
        write_json(path, evidence)
        return path

    def test_normalization(self):
        self.assertEqual(normalize_url('/product?page=2'), normalize_url('/product/page/2'))
        self.assertEqual(normalize_url('/product/?page=1'), 'https://en.delancable.com/product')
        with self.assertRaises(ValueError): normalize_url('/product?category=1')
        with self.assertRaises(ValueError): normalize_url('https://example.com/product/1')

    def test_extraction_excludes_boilerplate_and_image_certifications(self):
        p = extract(RAW, URL)
        self.assertEqual(len(p['facts']), 4)
        self.assertNotIn('warranty', p['detail_text'])
        self.assertFalse(p['conflicts'])
        self.assertEqual(p['facts'][-1]['text'], 'Jacket: TPU, TPE optional')

    def test_conflicting_parameters(self):
        raw = RAW.replace(b'</article>', b'<p>Insulation: PVC</p></article>')
        self.assertTrue(extract(raw, URL)['conflicts'])

    def test_full_pagination_discovery_dedupes_aliases_not_titles(self):
        def listing(pid, pages):
            return (f'<li class="news-item"><a href="/product/{pid}">Same title</a></li>' +
                    '<nav class="pagination">' + ''.join(f'<a href="{p}">Next</a>' for p in pages) + '</nav>').encode()
        source = {'https://en.delancable.com/product': listing(1, ['/product?page=2']),
                  'https://en.delancable.com/product/page/2': listing(2, ['/product/page/3', '/product?page=1']),
                  'https://en.delancable.com/product/page/3': listing(3, [])}
        with patch('scrape_product.fetch', side_effect=lambda u: source[u]):
            candidates = discover(self.root)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(read_json(self.root / 'catalog.json')['page_count'], 3)

    def test_catalog_failure_never_returns_partial_pool(self):
        with patch('scrape_product.fetch', side_effect=TimeoutError('offline failure')):
            with self.assertRaises(TimeoutError): discover(self.root)
        self.assertEqual(read_json(self.root / 'catalog.json')['status'], 'blocked')

    def test_copy_structure(self):
        self.assertGreaterEqual(validate_copy(COPY, URL)['body_words'], 80)
        with self.assertRaises(ValueError): validate_copy(COPY.replace(URL, TARGET_URL), URL)

    def test_minimum_image_size(self):
        path = self.root / 'small.webp'
        Image.new('RGB', (500,500)).save(path)
        with self.assertRaises(RuntimeError): validate(path, 'social', 750*1024)

    def test_metadata_removed(self):
        image = Image.new('RGB', (1024,1024))
        image.info['icc_profile'] = b'test-profile'
        path = self.root / 'clean.webp'
        path.write_bytes(encode_webp(strip_metadata(image), 88))
        self.assertTrue(validate(path, 'social', 750*1024)['metadata_removed'])

    def test_dry_run_cannot_submit_or_complete(self):
        manifest = self.campaign('dry-run')
        with self.assertRaises(ValueError): update(manifest, 'pending', submission_started=True)
        with self.assertRaises(ValueError): complete(manifest)

    def test_mutated_assets_cannot_submit(self):
        manifest = self.campaign()
        with (manifest.parent / 'facebook.txt').open('a') as f: f.write('\nChanged')
        with self.assertRaises(ValueError): update(manifest, 'pending', submission_started=True)

    def test_wrong_identity_cannot_submit(self):
        manifest = self.campaign()
        path = manifest.parent / 'evidence/preflight.json'
        evidence = read_json(path); evidence['target_url'] = 'https://www.facebook.com/other'
        write_json(path, evidence)
        with self.assertRaises(ValueError): update(manifest, 'pending', submission_started=True)

    def test_submission_disables_reselection_and_speculative_retry(self):
        manifest = self.campaign()
        update(manifest, 'pending', submission_started=True)
        update(manifest, 'uncertain', error='Synthetic timeout')
        with self.assertRaises(ValueError): retry(manifest, 'Cannot reselect')
        with self.assertRaises(ValueError): update(manifest, 'pending', submission_started=True)

    def test_one_reconciled_retry_only(self):
        manifest = self.campaign()
        update(manifest, 'pending', submission_started=True)
        evidence = manifest.parent / 'evidence/reconciliation.json'
        write_json(evidence, {'target_url':TARGET_URL,'checked_at':now(),'confirmed_absent':True,'no_pending_submission':True,'notes':'Synthetic absence evidence','evidence_file':'evidence/test-observation.txt'})
        update(manifest, 'pending', submission_started=True, reconciliation=evidence)
        with self.assertRaises(ValueError): update(manifest, 'pending', submission_started=True, reconciliation=evidence)

    def test_published_requires_submission_and_permalink(self):
        manifest = self.campaign()
        with self.assertRaises(ValueError): update(manifest, 'published', url=POST, evidence=self.publication(manifest))
        with self.assertRaises(ValueError): validate_permalink(TARGET_URL)
        with self.assertRaises(ValueError): validate_permalink('https://www.facebook.com/other/posts/123')

    def test_complete_then_cleanup_transport(self):
        manifest = self.campaign()
        update(manifest, 'pending', submission_started=True)
        update(manifest, 'published', url=POST, evidence=self.publication(manifest))
        record(manifest, 'reported', self.reporting(manifest))
        self.assertEqual(complete(manifest)['status'], 'complete')
        (manifest.parent / 'social-upload.jpg').unlink()
        self.assertEqual(complete(manifest)['status'], 'complete')
        with self.assertRaises(ValueError): update(manifest, 'pending', submission_started=True)

    def test_publication_without_reporting_cannot_complete(self):
        manifest = self.campaign()
        update(manifest, 'pending', submission_started=True)
        update(manifest, 'published', url=POST, evidence=self.publication(manifest))
        with self.assertRaisesRegex(ValueError, 'reporting is not verified'):
            complete(manifest)
        fb = read_json(manifest)['channels']['facebook']
        record(manifest, 'blocked', error='Synthetic Sheets access failure')
        self.assertEqual(read_json(manifest)['channels']['facebook'], fb)
        with self.assertRaises(ValueError): update(manifest, 'pending', submission_started=True)

    def test_reporting_rejects_wrong_destination_or_duplicates(self):
        manifest = self.campaign()
        update(manifest, 'pending', submission_started=True)
        update(manifest, 'published', url=POST, evidence=self.publication(manifest))
        for change in [lambda e: e['readback'].update(spreadsheetId='wrong'),
                       lambda e: e['search'].update(matched_row_count=2),
                       lambda e: e['search'].update(scanned_range='A1:E5'),
                       lambda e: e['readback']['sheets'][0]['data'][0]['rowData'][1]['values'][3].update(userEnteredValue={'stringValue': 'https://example.com/wrong'})]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                record(manifest, 'reported', self.reporting(manifest, change))

    def test_reporting_is_idempotent_and_tampering_blocks_completion(self):
        manifest = self.campaign()
        update(manifest, 'pending', submission_started=True)
        update(manifest, 'published', url=POST, evidence=self.publication(manifest))
        evidence = self.reporting(manifest)
        first = record(manifest, 'reported', evidence)
        self.assertEqual(first, record(manifest, 'reported', evidence))
        self.assertEqual(len(read_json(manifest)['reporting_history']), 1)
        self.assertEqual(complete(manifest)['google_sheet_row'], 2)
        with self.assertRaises(ValueError): record(manifest, 'failed', error='Cannot downgrade')
        tampered = read_json(evidence)
        tampered['row_number'] = 3
        write_json(evidence, tampered)
        with self.assertRaises(ValueError): complete(manifest)

    def test_dry_run_and_unpublished_runs_cannot_report(self):
        for mode in ['dry-run', 'live']:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                record(self.campaign(mode), 'blocked', error='Not a live published result')

    def test_completion_detects_changed_canonical_file(self):
        manifest = self.campaign()
        update(manifest, 'pending', submission_started=True)
        update(manifest, 'published', url=POST, evidence=self.publication(manifest))
        (manifest.parent / 'facebook.txt').write_text(COPY + '\nChanged')
        with self.assertRaises(ValueError): complete(manifest)

    def test_ten_candidate_budget_preserved(self):
        ledger = self.root / 'ledger.json'
        log = {'output_root':str(self.root),'mode':'dry-run','attempts':[], 'max_candidates':10,
               'candidates':[{'url':f'https://en.delancable.com/product/{i}'} for i in range(12)]}
        with patch('scrape_product.fetch', return_value=RAW), patch('scrape_product.extract', side_effect=CandidateError('invalid product')):
            with self.assertRaises(CandidateError): select(ledger, log)
        self.assertEqual(len(read_json(ledger)['attempts']), 10)

    def sheet_source(self, rows=None, mappings=None):
        source = self.root / 'sheet-source.json'
        write_json(source, {'checked_at':now(), 'metadata':{'spreadsheetId':SPREADSHEET_ID,
                   'properties':{'title':'social-auto-upload'}, 'sheets':[{'properties':{'sheetId':0,
                   'title':'工作表1','gridProperties':{'rowCount':1000}}}]},
                   'rows':{'range':"'工作表1'!A1:E1000",'values':[HEADERS]+(rows or [])},
                   'post_mappings':mappings or []})
        return source

    def test_sheet_history_requires_fresh_complete_correct_source(self):
        for change in [lambda b:b.update(checked_at='2000-01-01T00:00:00+00:00'),
                       lambda b:b['rows'].update(range="'工作表1'!A1:E10"),
                       lambda b:b['metadata'].update(spreadsheetId='wrong'),
                       lambda b:b['rows'].update(values=[['wrong header']])]:
            source = self.sheet_source(); data = read_json(source); change(data); write_json(source,data)
            with self.subTest(change=change), self.assertRaises(ValueError): build_history(self.root,source)
        snapshot = build_history(self.root)
        with self.assertRaisesRegex(ValueError, 'both local'): check_history(snapshot,self.root)

    def test_unmapped_sheet_post_blocks_until_evidence_mapping(self):
        rows = [['en.delancable.com','2026-01-01 09:00:00','不适用',POST,'不适用']]
        source = self.sheet_source(rows)
        history = build_history(self.root,source)
        self.assertEqual(history['status'],'blocked')
        with self.assertRaises(ValueError): check_history(history,self.root)
        proof = self.root/'post.txt'; proof.write_text('Synthetic offline post observation')
        mapping = {'post_url':POST,'product_url':URL+'/?utm_source=fb','verified_at':now(),
                   'author_matches':True,'product_link_verified':True,'copy':COPY,'evidence_file':'post.txt'}
        source = self.sheet_source(rows,[mapping])
        history = build_history(self.root,source)
        self.assertEqual(check_history(history,self.root),{URL})
        self.assertEqual(len(history['recent_posts']),1)

    def test_local_published_maps_sheet_and_reporting_failure_stays_excluded(self):
        m=self.campaign();update(m,'pending',submission_started=True)
        update(m,'published',url=POST,evidence=self.publication(m))
        record(m,'blocked',error='Synthetic Sheets failure')
        source=self.sheet_source([['en.delancable.com','date','不适用',POST+'?tracking=1','不适用']])
        h=build_history(self.root,source)
        self.assertEqual(h['status'],'ready')
        self.assertEqual(h['excluded_product_urls'],[URL])
        self.assertEqual(len(h['records']),1)

    def test_uncertain_and_failed_submissions_reserved_but_drafts_not(self):
        m=self.campaign()
        self.assertFalse(local_records(self.root))
        update(m,'pending',submission_started=True)
        update(m,'failed',error='Synthetic interrupted submit')
        self.assertEqual(local_records(self.root)[0]['state'],'reserved')
        h=build_history(self.root)
        self.assertEqual(h['excluded_product_urls'],[URL])
        self.assertEqual(product_key(URL+'/?fbclid=test'),URL)
        self.assertEqual(post_key(POST+'/?tracking=1'),POST)

    def test_no_candidate_fetch_when_all_products_are_historical(self):
        m=self.campaign();update(m,'pending',submission_started=True)
        history=build_history(self.root,self.sheet_source())
        log={'output_root':str(self.root),'mode':'live','attempts':[],'max_candidates':10,
             'publication_history':history,'candidates':[{'url':URL}]}
        with patch('scrape_product.fetch') as fetcher:
            with self.assertRaises(CandidateError):select(self.root/'ledger.json',log)
        fetcher.assert_not_called()
        self.assertEqual(log['attempts'],[])
        self.assertEqual(len(log['skipped_history']),1)

    def test_selection_skips_published_before_fetching_new_candidate(self):
        m=self.campaign();update(m,'pending',submission_started=True)
        h=build_history(self.root,self.sheet_source())
        image=io.BytesIO();Image.new('RGB',(300,300)).save(image,format='PNG')
        new_url='https://en.delancable.com/product/12345'
        log={'output_root':str(self.root),'mode':'live','attempts':[],'max_candidates':10,
             'publication_history':h,'candidates':[{'url':URL},{'url':new_url}]}
        with patch('scrape_product.fetch',side_effect=[RAW,image.getvalue()]) as fetcher:
            chosen=select(self.root/'ledger.json',log)
        self.assertEqual(chosen['product_url'],new_url)
        self.assertEqual(fetcher.call_args_list[0].args[0],new_url)
        self.assertEqual(chosen['candidates_tried'],1)

    def test_two_prepared_runs_cannot_submit_same_product(self):
        first,second=self.campaign(),self.campaign()
        update(first,'pending',submission_started=True)
        # Second snapshot was taken before first submission; live root recheck still blocks it.
        with self.assertRaisesRegex(ValueError,'already published or reserved'):
            update(second,'pending',submission_started=True)
        self.assertEqual(read_json(second).get('submission_count',0),0)

    def test_optional_ai_label_must_not_be_enabled_without_specific_basis(self):
        m=self.campaign();p=m.parent/'evidence/preflight.json';d=read_json(p)
        d['ai_label']={'value':'on','reason':'Used imagegen'};write_json(p,d)
        with self.assertRaisesRegex(ValueError,'optional AI label'):update(m,'pending',submission_started=True)
        d['ai_label'].update(basis='platform_required',evidence='Synthetic mandatory disclosure screen')
        write_json(p,d);self.assertEqual(update(m,'pending',submission_started=True)['submission_count'],1)

    def test_copy_novelty_rejects_model_swap_and_accepts_different_angle(self):
        with self.assertRaises(ValueError):check_copy_novelty(COPY.replace('signal cable','power cable'),[{'copy':COPY}])
        result=check_copy_novelty('Compare pair count and the available routing space before specifying this cable.',[{'copy':COPY}])
        self.assertLess(result['max_similarity'],0.82)

    def test_v2_campaign_retains_original_copy_format_and_new_review(self):
        m=self.campaign();d=read_json(m);d['version']=2;write_json(m,d)
        h=build_history(self.root,self.sheet_source());write_json(m.parent/d['selection_history'],h)
        p=m.parent/'evidence/copy-review.json';r=read_json(p)
        r.update(angle='Insulation and jacket options',recent_posts_reviewed=[],distinct_from_recent='First offline fixture, no earlier posts')
        write_json(p,r)
        result=inspect_campaign(m)
        self.assertEqual(result['copy']['feature_lines'],4)
        self.assertEqual(result['copy']['hashtags'],8)
        self.assertIn(d['selection_history'],result['hashes'])
        with self.assertRaises(ValueError):validate_copy(COPY.replace('🔌','',1),URL)
        write_json(m.parent/'evidence/campaign-validation.json',result)
        update(m,'pending',submission_started=True)
        rec=m.parent/'evidence/reconciliation.json'
        write_json(rec,{'target_url':TARGET_URL,'checked_at':now(),'confirmed_absent':True,'no_pending_submission':True,
                       'notes':'Synthetic absence evidence','evidence_file':'evidence/test-observation.txt'})
        h=build_history(self.root,self.sheet_source(),exclude=m)
        write_json(m.parent/'evidence/history-preflight.json',h)
        self.assertEqual(update(m,'pending',submission_started=True,reconciliation=rec)['submission_count'],2)
        update(m,'published',url=POST,evidence=self.publication(m))
        record(m,'reported',self.reporting(m))
        self.assertEqual(complete(m)['status'],'complete')
        h['checked_at']=now();write_json(m.parent/'evidence/history-preflight.json',h)
        with self.assertRaisesRegex(ValueError,'preflight is missing or changed'):complete(m)

    def test_metadata_roundtrip_and_raw_container_rejection(self):
        image=Image.new('RGB',(1024,1024));exif=Image.Exif();exif[270]='Private comment';exif[315]='Author'
        raw=self.root/'tagged.png'
        image.save(raw,exif=exif,xmp=b'<metadata>test</metadata>',icc_profile=b'profile')
        with Image.open(raw) as original:clean=strip_metadata(original)
        webp=self.root/'clean.webp';webp.write_bytes(encode_webp(clean,88))
        jpeg=self.root/'clean.jpg';create_transport_jpeg(clean,jpeg)
        self.assertTrue(validate(webp,'social',750*1024)['metadata_removed'])
        self.assertTrue(validate_transport(jpeg,(1024,1024))['metadata_removed'])
        original=jpeg.read_bytes()
        for marker in (225,237,235,254):  # EXIF/XMP, IPTC, JUMBF, comment containers.
            payload=b'synthetic-metadata';segment=bytes([255,marker])+(len(payload)+2).to_bytes(2,'big')+payload
            jpeg.write_bytes(original[:2]+segment+original[2:])
            with self.subTest(marker=marker),self.assertRaises(RuntimeError):validate_transport(jpeg)
        data=webp.read_bytes();chunk=b'JUMB'+(4).to_bytes(4,'little')+b'test'
        tagged=data+chunk;tagged=tagged[:4]+(len(tagged)-8).to_bytes(4,'little')+tagged[8:];webp.write_bytes(tagged)
        with self.assertRaises(RuntimeError):validate(webp,'social',750*1024)


if __name__ == '__main__':
    unittest.main()
