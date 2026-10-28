#!/usr/bin/env python3
"""Merge local submission history with a fresh, bounded Sheets read. Never publishes."""
from __future__ import annotations
import argparse
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from common import SKILL, TARGET_URL, now, read_json, recent, sha256, submitted, timestamp, write_json
from record_reporting import HEADERS, SHEET_TITLE, SPREADSHEET_ID


def product_key(url):
    p = urlparse(url)
    if (p.scheme not in {'http', 'https'} or p.hostname != 'en.delancable.com' or
            p.username or p.password or p.port not in {None, 80, 443} or
            not re.fullmatch(r'/product/\d+/?', p.path)):
        raise ValueError('History requires a Delan product detail URL')
    return 'https://en.delancable.com' + p.path.rstrip('/')


def post_key(url):
    p = urlparse(url)
    if (p.scheme != 'https' or p.hostname not in {'facebook.com', 'www.facebook.com', 'm.facebook.com'} or
            p.username or p.password or p.port not in {None, 443}):
        raise ValueError('History requires a Facebook permalink')
    if re.fullmatch(r'/[^/]+/posts/[^/]+/?', p.path):
        return 'https://www.facebook.com' + p.path.rstrip('/')
    q = parse_qs(p.query)
    if p.path in {'/permalink.php', '/story.php'} and q.get('id') and q.get('story_fbid'):
        return 'https://www.facebook.com/permalink.php?id=' + q['id'][0] + '&story_fbid=' + q['story_fbid'][0]
    raise ValueError('History URL is not an individual Facebook post')


def local_records(root, exclude=None):
    records = []
    for path in sorted(Path(root).glob('*/manifest.json')):
        if exclude and path.resolve() == Path(exclude).resolve():
            continue
        m = read_json(path)  # A broken local manifest must not silently disappear from history.
        if m.get('skill') != SKILL or m.get('target_url') != TARGET_URL or m.get('mode') != 'live':
            continue
        fb = m.get('channels', {}).get('facebook', {})
        if not submitted(m):
            continue
        published = fb.get('status') == 'published'
        item = {'product_url': product_key(m['product']['canonical_url']),
                'title': m['product'].get('title', ''), 'state': 'published' if published else 'reserved',
                'manifest': str(path.resolve()), 'manifest_sha256': sha256(path),
                'post_url': post_key(fb['url']) if published and fb.get('url') else '',
                'at': fb.get('publication', {}).get('verified_at', m.get('submission_started_at', ''))}
        copy = path.parent / m.get('artifacts', {}).get('facebook_copy', 'facebook.txt')
        if copy.is_file() and path.parent.resolve() in copy.resolve().parents:
            item['copy'] = copy.read_text(encoding='utf-8')
        records.append(item)
    return records


def build_history(root, sheet_source=None, exclude=None):
    root = Path(root).resolve()
    records = local_records(root, exclude)
    report = {'version': 1, 'target_url': TARGET_URL, 'output_root': str(root),
              'checked_at': now(), 'coverage': 'local_only', 'records': records,
              'unresolved_posts': [], 'sources': {}}
    if sheet_source:
        source = Path(sheet_source).resolve()
        bundle = read_json(source)
        recent(bundle.get('checked_at', ''))
        meta, grid = bundle['metadata'], bundle['rows']
        tabs = [s['properties'] for s in meta.get('sheets', [])
                if s['properties'].get('sheetId') == 0 and s['properties'].get('title') == SHEET_TITLE]
        if meta.get('spreadsheetId') != SPREADSHEET_ID or meta.get('properties', {}).get('title') != 'social-auto-upload' or len(tabs) != 1:
            raise ValueError('History source is not the configured spreadsheet and sheet')
        count = tabs[0]['gridProperties']['rowCount']
        if count * 5 > 50000 or grid.get('range') != f"'{SHEET_TITLE}'!A1:E{count}" or grid.get('majorDimension', 'ROWS') != 'ROWS':
            raise ValueError('History needs the complete bounded A:E read within 50000 cells')
        rows = grid.get('values', [])
        if not rows or rows[0][:5] != HEADERS or len(rows) > count:
            raise ValueError('History headers or row bounds do not match')
        mapping = {}
        for rec in records:
            if rec['post_url']:
                old = mapping.setdefault(rec['post_url'], rec)
                if old['product_url'] != rec['product_url']:
                    raise ValueError('Conflicting local product mappings for one Facebook post')
        for rec in bundle.get('post_mappings', []):
            # For Sheet posts without a local manifest, the operator must inspect that public post.
            key, product = post_key(rec['post_url']), product_key(rec['product_url'])
            proof = (source.parent / rec['evidence_file']).resolve()
            if (rec.get('author_matches') is not True or rec.get('product_link_verified') is not True or
                    not rec.get('copy') or not rec.get('verified_at') or not proof.is_file() or not proof.stat().st_size):
                raise ValueError('An external post mapping requires observed author, product link, copy and evidence')
            if key in mapping and mapping[key]['product_url'] != product:
                raise ValueError('Conflicting product mapping for one Facebook post')
            timestamp(rec['verified_at'])
            mapping[key] = dict(rec, post_url=key, product_url=product, state='published', at=rec['verified_at'])
            report['sources'][str(proof)] = sha256(proof)
        for number, row in enumerate(rows[1:], 2):
            if not row or str(row[0] or '').strip().lower() not in {'en.delancable.com', 'delancable.com', 'www.delancable.com'}:
                continue
            if len(row) < 4 or not row[3]:
                report['unresolved_posts'].append({'row': number, 'reason': 'Missing Facebook permalink'})
                continue
            key = post_key(row[3])
            if key not in mapping or not mapping[key].get('copy'):
                report['unresolved_posts'].append({'row': number, 'post_url': row[3], 'reason': 'Read this post to recover its product URL and copy'})
                continue
            rec = dict(mapping[key], sheet_row=number)
            if not any(r.get('post_url') == key for r in records):
                records.append(rec)
            else:
                # A verified mapping may restore the missing copy for a known local product.
                for local in records:
                    if local.get('post_url') == key and not local.get('copy'):
                        local['copy'] = rec['copy']
        report.update(coverage='local_and_sheet', sheet_checked_at=bundle['checked_at'])
        report['sources'][str(source)] = sha256(source)
    report['excluded_product_urls'] = sorted({r['product_url'] for r in records})
    report['recent_posts'] = sorted([r for r in records if r['state'] == 'published'], key=lambda r: r.get('at', ''), reverse=True)[:5]
    report['status'] = 'blocked' if report['unresolved_posts'] else 'ready'
    return report


def check_history(report, root, live=True, fresh=True):
    if report.get('target_url') != TARGET_URL or Path(report.get('output_root', '')).resolve() != Path(root).resolve():
        raise ValueError('History belongs to another target or output root')
    if report.get('status') != 'ready' or report.get('unresolved_posts'):
        raise ValueError('Resolve unmatched history posts before selection/submission')
    if live and report.get('coverage') != 'local_and_sheet':
        raise ValueError('Live selection requires both local and Google Sheets history')
    if fresh:
        recent(report.get('checked_at', ''))
        if live:
            recent(report.get('sheet_checked_at', ''))
        for path, digest in report.get('sources', {}).items():
            if not Path(path).is_file() or sha256(Path(path)) != digest:
                raise ValueError('History source changed; rebuild the history snapshot')
    expected = sorted({product_key(r['product_url']) for r in report['records']})
    if expected != report.get('excluded_product_urls'):
        raise ValueError('History exclusions do not match its records')
    return set(expected)


def body(text):
    text = re.sub(r'https?://\S+|#[\w]+', '', text)
    return ' '.join(re.findall(r'[a-z0-9]+', text.lower()))


def check_copy_novelty(text, records):
    normalized = body(text)
    maximum = 0.0
    for rec in records:
        if not rec.get('copy'):
            continue
        old = body(rec['copy'])
        score = SequenceMatcher(None, normalized, old, autojunk=False).ratio()
        maximum = max(maximum, score)
        if normalized == old or score >= 0.82:
            raise ValueError('Copy duplicates or closely repeats an earlier submission; rewrite the angle and wording')
    return {'compared_posts': sum(bool(r.get('copy')) for r in records), 'max_similarity': round(maximum, 3)}


def guard_submission(path, manifest, preflight):
    root = Path(path).resolve().parent
    evidence = root / 'evidence/history-preflight.json'
    snapshot = read_json(evidence)
    excluded = check_history(snapshot, root.parent)
    # Read again under the shared output-root lock: another run may have submitted since the snapshot.
    current = local_records(root.parent, exclude=path)
    excluded.update(r['product_url'] for r in current)
    if product_key(manifest['product']['canonical_url']) in excluded:
        raise ValueError('Product already published or reserved by another submission; do not post again')
    novelty = check_copy_novelty((root / manifest['artifacts']['facebook_copy']).read_text(), snapshot['records'] + current)
    label = preflight.get('ai_label', {})
    if label.get('value') not in {'off', 'unavailable', 'on'} or not label.get('reason'):
        raise ValueError('Record the actual optional AI label state and reason in preflight')
    if label['value'] == 'on' and (label.get('basis') not in {'platform_required', 'user_requested'} or not label.get('evidence')):
        raise ValueError('Do not enable an optional AI label by default')
    return {'history_sha256': sha256(evidence), 'checked_at': now(), 'novelty': novelty,
            'ai_label': label}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-root', required=True, type=Path)
    p.add_argument('--sheet-evidence', type=Path)
    p.add_argument('--exclude-manifest', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    report = build_history(a.output_root, a.sheet_evidence, a.exclude_manifest)
    write_json(a.output, report)
    print(f"{report['status']}: {len(report['excluded_product_urls'])} excluded products, "
          f"{len(report['unresolved_posts'])} unresolved posts; {a.output}")
    if report['status'] != 'ready':
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
