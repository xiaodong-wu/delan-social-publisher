#!/usr/bin/env python3
"""Read the complete Delan catalog and prepare one auditable Facebook campaign. Never publishes."""
from __future__ import annotations
import argparse
import io
import json
import random
import re
import sys
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from uuid import uuid4
from PIL import Image, UnidentifiedImageError
from common import CATALOG_URL, SKILL, TARGET_URL, load_manifest, now, read_json, submitted, write_json
from publication_history import build_history, check_history, product_key

SITE = 'en.delancable.com'
ASSET_HOSTS = {SITE, 'static.dcodingmax.com'}
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class CandidateError(ValueError):
    pass


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def normalize_url(value, base=CATALOG_URL):
    p = urlparse(urljoin(base, value))
    if p.scheme not in {'https', 'http'} or p.hostname != SITE or p.username or p.password or p.port not in {None, 80, 443}:
        raise ValueError('Only the Delan English product site is allowed')
    path = p.path.rstrip('/')
    if re.fullmatch(r'/product/\d+', path):
        return f'https://{SITE}{path}'
    page_path = re.fullmatch(r'/product/page/(\d+)', path)
    if path != '/product' and not page_path:
        raise ValueError('Not a product or catalog URL')
    params = dict(parse_qsl(p.query))
    if set(params) - {'page'}:
        raise ValueError('Ignore category filters and unrelated query parameters')
    page = page_path[1] if page_path else params.get('page', '1')
    if not page.isdigit() or int(page) < 1:
        raise ValueError('Invalid catalog page')
    return CATALOG_URL + (f'/page/{int(page)}' if int(page) > 1 else '')


def asset_url(value, base):
    p = urlparse(urljoin(base, value))
    if p.scheme != 'https' or p.hostname not in ASSET_HOSTS or p.username or p.password or p.port not in {None, 443}:
        raise CandidateError('Product image is not from the observed Delan/CDN hosts')
    return urlunparse(p._replace(path=quote(p.path, safe='/%:@'), query=quote(p.query, safe='/%!|=:&,;+')))


def fetch(url, image=False):
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; DelanSocialPublisher/1.0)'}), timeout=30) as response:
        final = urlparse(response.url)
        hosts = ASSET_HOSTS if image else {SITE}
        if final.scheme != 'https' or final.hostname not in hosts:
            raise RuntimeError('Unexpected off-site redirect')
        data = response.read(25 * 1024 * 1024 + 1)
        if len(data) > 25 * 1024 * 1024:
            raise RuntimeError('Source exceeds the 25 MiB read limit')
        return data


class ProductParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.anchors, self.blocks = [], [], []
        self.title, self.canonical, self.hero = '', '', ''

    def within(self, cls):
        return any(cls in n['classes'] for n in self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and 'canonical' in (attrs.get('rel') or '').split():
            self.canonical = attrs.get('href', '')
        if tag == 'img' and self.within('xmdsite-head-cover') and not self.hero:
            self.hero = attrs.get('src', '')
        if tag in VOID:
            return
        self.stack.append({'tag': tag, 'attrs': attrs, 'classes': (attrs.get('class') or '').split(),
                           'parts': [], 'in_body': self.within('xmdsite-article'),
                           'in_card': self.within('news-item'), 'in_pager': self.within('pagination')})

    def handle_data(self, data):
        if any(n['tag'] in {'script', 'style', 'noscript'} for n in self.stack):
            return
        for node in self.stack:
            node['parts'].append(data)

    def finish(self, node):
        text = clean(''.join(node['parts']))
        if node['tag'] == 'h1' and 'xmdsite-item-title' in node['classes']:
            self.title = text
        if node['tag'] == 'a':
            self.anchors.append({'href': node['attrs'].get('href', ''), 'text': text,
                                 'card': node['in_card'], 'pager': node['in_pager']})
        if node['in_body'] and node['tag'] in {'p', 'li', 'tr'} and text:
            self.blocks.append(text)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]['tag'] == tag:
                while len(self.stack) > i:
                    self.finish(self.stack.pop())
                return


def parse(raw):
    parser = ProductParser()
    parser.feed(raw.decode('utf-8', errors='replace'))
    parser.close()
    return parser


def discover(directory):
    audit = {'catalog_url': CATALOG_URL, 'status': 'scanning', 'started_at': now(), 'pages': [], 'candidates': []}
    audit_path = directory / 'catalog.json'
    queue, visited, pool = deque([CATALOG_URL]), {CATALOG_URL}, {}
    try:
        while queue:
            url = queue.popleft()
            entry = {'url': url, 'status': 'checking'}
            audit['pages'].append(entry)
            write_json(audit_path, audit)
            try:
                raw = fetch(url)
            except HTTPError as exc:
                if url != CATALOG_URL and exc.code in {404, 410}:
                    entry.update(status='not_found', http_status=exc.code)
                    continue
                raise
            snapshot = directory / f'catalog-page-{len(audit["pages"]):02d}.html'
            snapshot.write_bytes(raw)
            parser = parse(raw)
            products, links = set(), set()
            for a in parser.anchors:
                try:
                    normalized = normalize_url(a['href'], url)
                except ValueError:
                    continue
                if a['card'] and re.fullmatch(r'/product/\d+', urlparse(normalized).path):
                    products.add(normalized)
                    item = pool.setdefault(normalized, {'url': normalized, 'title': '', 'listing_pages': []})
                    if a['text'] and a['text'] != 'Product details':
                        item['title'] = a['text']
                    if url not in item['listing_pages']:
                        item['listing_pages'].append(url)
                elif a['pager'] and re.fullmatch(r'/product(?:/page/\d+)?', urlparse(normalized).path):
                    links.add(normalized)
                    if normalized not in visited:
                        queue.append(normalized)
                        visited.add(normalized)
            entry.update(product_count=len(products), pagination_urls=sorted(links), source_html=str(snapshot))
            if not products:
                raise RuntimeError(f'Catalog template changed or no product cards: {url}')
            entry['status'] = 'fetched'
        audit.update(status='complete', completed_at=now(), candidates=list(pool.values()),
                     candidate_count=len(pool), page_count=sum(p['status'] == 'fetched' for p in audit['pages']))
    except Exception as exc:
        audit.update(status='blocked', error=str(exc))
        raise
    finally:
        write_json(audit_path, audit)
    return audit['candidates']


def extract(raw, url):
    parser = parse(raw)
    if not parser.title or not parser.hero:
        raise CandidateError('Missing product title or product cover image')
    canonical = normalize_url(parser.canonical or url)
    if canonical != url:
        raise CandidateError('Canonical URL does not match the requested product ID')
    facts, fields, conflicts = [], {}, []
    for block in dict.fromkeys(parser.blocks):
        if block.endswith(':') or block.endswith('：'):
            continue
        fact = {'id': f'f{len(facts)+1:02d}', 'text': block, 'source': 'article.xmdsite-article', 'source_url': url}
        key, sep, val = block.partition(':')
        if sep and key and val.strip():
            key, val = clean(key).casefold(), clean(val)
            fact.update(label=key, value=val)
            if key in fields and fields[key].casefold() != val.casefold():
                conflicts.append({'label': key, 'values': [fields[key], val]})
            fields[key] = val
        facts.append(fact)
    return {'source_url': url, 'canonical_url': canonical, 'title': parser.title,
            'retrieved_at': now(), 'facts': facts, 'conflicts': conflicts,
            'detail_text': '\n'.join(parser.blocks), 'hero_image_url': asset_url(parser.hero, url),
            'review_required': True}


def prepare_run(root, product, raw, image_data, suffix, ledger, mode, history=None):
    pid = product['canonical_url'].rsplit('/', 1)[-1]
    run = root / (now()[:19].replace(':', '').replace('-', '') + '-' + pid + '-' + uuid4().hex[:6])
    (run / 'source').mkdir(parents=True)
    (run / 'evidence').mkdir()
    (run / 'source/page.html').write_bytes(raw)
    hero = 'source/hero.' + suffix
    (run / hero).write_bytes(image_data)
    write_json(run / 'product.json', product)
    write_json(run / 'evidence/product-review.json', {'status': 'pending', 'usable_fact_ids': [], 'conflicts': product['conflicts'], 'notes': ''})
    if history is not None:
        write_json(run / 'evidence/selection-history.json', history)
    manifest = {'version': 3, 'skill': SKILL, 'run_id': run.name, 'mode': mode,
                'created_at': now(), 'status': 'prepared', 'target_url': TARGET_URL,
                'product': {'title': product['title'], 'canonical_url': product['canonical_url']},
                'artifacts': {'product': 'product.json', 'source_html': 'source/page.html', 'source_hero': hero,
                              'facebook_copy': 'facebook.txt', 'social_image': 'social.webp', 'social_transport': 'social-upload.jpg'},
                'selection_log': str(ledger), 'channels': {'facebook': {'status': 'pending'}}, 'history': [],
                'reporting': {'google_sheet': {'status': 'pending' if mode == 'live' else 'not_applicable'}}}
    manifest['selection_history'] = 'evidence/selection-history.json'
    write_json(run / 'manifest.json', manifest)
    return run / 'manifest.json'


def select(ledger_path, log):
    # Run before touching any candidate. A stale/partial history is not an empty history.
    history = log.get('publication_history')
    excluded = check_history(history, log['output_root'], live=log['mode'] == 'live') if history else set()
    if log['mode'] == 'live' and history is None:
        raise ValueError('Live selection requires a fresh publication history snapshot')
    log['skipped_history'] = [c for c in log['candidates'] if product_key(c['url']) in excluded]
    tried = {x['url'] for x in log['attempts']}
    for candidate in log['candidates']:
        url = candidate['url']
        if product_key(url) in excluded or url in tried or len(log['attempts']) >= log['max_candidates']:
            continue
        record = {'url': url, 'status': 'checking', 'checked_at': now()}
        log['attempts'].append(record)
        write_json(ledger_path, log)
        try:
            raw = fetch(url)
            (ledger_path.parent / f'candidate-{len(log["attempts"]):02d}.html').write_bytes(raw)
            product = extract(raw, url)
            write_json(ledger_path.parent / f'candidate-{len(log["attempts"]):02d}.json', product)
            if len(product['facts']) < 4 or product['conflicts']:
                raise CandidateError('Fewer than four facts or conflicting duplicate parameters')
            image_data = fetch(product['hero_image_url'], image=True)
            try:
                with Image.open(io.BytesIO(image_data)) as image:
                    image.verify()
                with Image.open(io.BytesIO(image_data)) as image:
                    suffix = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(image.format)
                    if not suffix or min(image.size) < 200:
                        raise CandidateError('Product hero must be recognizable raster content at least 200px per side')
            except (UnidentifiedImageError, OSError) as exc:
                raise CandidateError('Product hero cannot be decoded') from exc
            manifest = prepare_run(Path(log['output_root']), product, raw, image_data, suffix, ledger_path, log['mode'], history)
        except CandidateError as exc:
            record.update(status='rejected', reason=str(exc))
            write_json(ledger_path, log)
            continue
        except Exception as exc:
            record.update(status='blocked', reason=str(exc))
            log.update(status='blocked', reason='Network, filesystem or tool failure; do not reselect')
            write_json(ledger_path, log)
            raise
        record.update(status='selected', manifest=str(manifest), title=product['title'])
        log['status'] = 'selected'
        write_json(ledger_path, log)
        return {'manifest': str(manifest), 'run_dir': str(manifest.parent), 'product': product['title'],
                'product_url': url, 'selection_log': str(ledger_path), 'candidates_tried': len(log['attempts']),
                'catalog_count': len(log['candidates']), 'history_excluded': len(log['skipped_history'])}
    log.update(status='blocked', reason='No eligible unpublished product remains, or ten-candidate limit reached; do not automatically recycle published products')
    write_json(ledger_path, log)
    raise CandidateError(f'No qualified product; see {ledger_path}')


def retry(manifest_path, reason):
    manifest_path = manifest_path.resolve()
    data = load_manifest(manifest_path)
    if submitted(data):
        raise ValueError('Reselection permanently disabled after submission')
    ledger = Path(data['selection_log'])
    log = read_json(ledger)
    if log['targeted']:
        raise ValueError('Explicitly targeted product cannot be substituted')
    last = log['attempts'][-1]
    if last.get('manifest') != str(manifest_path) or last['status'] != 'selected':
        raise ValueError('Only the current selected candidate can be rejected')
    last.update(status='rejected', reason=reason)
    data['status'] = 'rejected'
    data['channels']['facebook'].update(status='blocked', error=reason)
    write_json(manifest_path, data)
    log['status'] = 'selecting'
    write_json(ledger, log)
    return ledger, log


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--product-url')
    p.add_argument('--output-root', type=Path)
    p.add_argument('--mode', choices=['live', 'dry-run'])
    p.add_argument('--retry-from', type=Path)
    p.add_argument('--reason')
    p.add_argument('--history', type=Path, help='Fresh publication_history.py snapshot; required for live runs')
    args = p.parse_args()
    if args.retry_from:
        if args.product_url or args.output_root or args.mode or not args.reason or not args.reason.strip():
            p.error('--retry-from requires --reason and no other selection overrides')
        ledger, log = retry(args.retry_from, args.reason)
        if args.history:
            log['publication_history'] = read_json(args.history)
    else:
        if args.reason:
            p.error('--reason requires --retry-from')
        root = (args.output_root or Path.cwd() / 'campaign-runs').expanduser().resolve()
        skill_root = Path(__file__).resolve().parents[1]
        if root == skill_root or skill_root in root.parents:
            raise ValueError('Campaign files must be outside the skill directory')
        directory = root / ('selection-' + now()[:19].replace(':', '').replace('-', '') + '-' + uuid4().hex[:6])
        directory.mkdir(parents=True)
        ledger = directory / 'selection-ledger.json'
        log = {'version': 1, 'output_root': str(root), 'targeted': bool(args.product_url),
               'mode': args.mode or 'live', 'status': 'selecting', 'max_candidates': 1 if args.product_url else 10,
               'attempts': [], 'candidates': [], 'created_at': now()}
        write_json(ledger, log)
        try:
            log['publication_history'] = read_json(args.history) if args.history else build_history(root)
            check_history(log['publication_history'], root, live=log['mode'] == 'live')
            if args.product_url:
                url = normalize_url(args.product_url)
                if not re.fullmatch(r'/product/\d+', urlparse(url).path):
                    raise ValueError('--product-url requires a product detail URL')
                log['candidates'] = [{'url': url}]
            else:
                log['candidates'] = discover(directory)
                random.SystemRandom().shuffle(log['candidates'])
                log['catalog'] = str(directory / 'catalog.json')
        except Exception as exc:
            log.update(status='blocked', reason=str(exc))
            write_json(ledger, log)
            raise
        write_json(ledger, log)
    print(json.dumps(select(ledger, log), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
