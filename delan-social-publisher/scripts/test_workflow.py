"""Offline regression checks. Fake platform evidence is confined to temporary test directories."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from common import TARGET_URL, now, read_json, validate_permalink, write_json
from optimize_image import strip_metadata, encode_webp, create_transport_jpeg, validate
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
        write_json(root / 'evidence/preflight.json', {'target_url':TARGET_URL, 'checked_at':now(), 'identity_confirmed':True,'can_create_post':True,'active_identity':'Fixture Delan', 'observed_page_id':'123456789','evidence_file':'evidence/test-observation.txt'})
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


if __name__ == '__main__':
    unittest.main()
