#!/usr/bin/env python3
"""Validate Delan Facebook copy, reviewed evidence and social assets; save hashes."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from common import load_manifest, local_file, now, read_json, sha256, submitted, timestamp, write_json
from optimize_image import validate, validate_transport
from publication_history import check_history, check_copy_novelty

WORD = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
TAG = re.compile(r'#[A-Za-z][A-Za-z0-9_]*')
EMOJI = ('🏭', '📦', '🛠', '⚙', '🔧', '✅', '💡', '📏', '🔌', '⚡', '🧵', '🛡', '🔗', '🔬', '🤖', '🔄')
WEBSITE = re.compile(r'(?:\b(?:https?|ftp)://\S+|\bwww\.\S+|'
                     r'(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?![\w-]))', re.I)


def validate_copy(text, url, version=3):
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    link_free = version >= 3
    if len(lines) < (7 if link_free else 8) or not all(line.startswith(EMOJI) for line in lines[:4]):
        raise ValueError('Start with exactly four emoji feature lines, then benefit, CTA and hashtags'
                         + ('' if link_free else ', with the legacy product URL before hashtags'))
    if any(line.startswith(EMOJI) for line in lines[4:]):
        raise ValueError('Only four feature lines are allowed')
    if link_free and WEBSITE.search(text):
        raise ValueError('Social copy must not contain website links, www addresses or bare domains')
    if not link_free and (lines[-2] != url or re.findall(r'https?://\S+', text) != [url]):
        raise ValueError('The sole URL must be the selected product link on the penultimate nonempty line')
    tags = TAG.findall(lines[-1])
    min_tags, max_tags = 8, 12
    if not min_tags <= len(tags) <= max_tags or len(set(t.casefold() for t in tags)) != len(tags) or TAG.sub('', lines[-1]).strip():
        raise ValueError(f'Last line must contain {min_tags}–{max_tags} unique English hashtags')
    if TAG.search('\n'.join(lines[:-1])):
        raise ValueError('Keep all hashtags on the final line')
    body = lines[:-1] if link_free else lines[:-2]
    words = len(WORD.findall('\n'.join(body)))
    lo, hi = 80, 150
    if not lo <= words <= hi or re.search(r'[\u3400-\u9fff]', text):
        raise ValueError(f'Copy must have {lo}–{hi} English body words, excluding URL/hashtags; found {words}')
    return {'body_words': words, 'feature_lines': sum(line.startswith(EMOJI) for line in body), 'hashtags': len(tags)}


def review(root, name):
    data = read_json(local_file(root, 'evidence/' + name + '-review.json'))
    if data.get('status') != 'approved' or not data.get('notes'):
        raise ValueError(f'{name} review must be approved with substantive notes')
    timestamp(data.get('reviewed_at', ''))
    return data


def inspect_campaign(path, allow_missing_transport=False):
    path = Path(path).resolve()
    root, data = path.parent, load_manifest(path)
    if data.get('status') == 'rejected':
        raise ValueError('Rejected candidates cannot be validated')
    paths = {k: local_file(root, v) for k, v in data['artifacts'].items()
             if not (allow_missing_transport and k == 'social_transport' and not (root / v).exists())}
    product = read_json(paths['product'])
    if data['product']['canonical_url'] != product['canonical_url'] or data['product']['title'] != product['title']:
        raise ValueError('Manifest and extracted product disagree')
    if product.get('conflicts'):
        raise ValueError('Unresolved source conflicts')
    text = paths['facebook_copy'].read_text(encoding='utf-8')
    version = data.get('version', 1)
    metrics = validate_copy(text, product['canonical_url'], version)
    source_review = review(root, 'product')
    allowed = source_review.get('usable_fact_ids', [])
    ids = {f['id'] for f in product['facts']}
    if len(set(allowed)) < 4 or not set(allowed) <= ids or source_review.get('conflicts') != []:
        raise ValueError('Product review must approve at least four valid facts and resolve no conflicts by guessing')
    copy_review = review(root, 'copy')
    claims = copy_review.get('claims', [])
    if copy_review.get('all_claims_checked') is not True or len(claims) < 4:
        raise ValueError('Copy review must trace all factual claims, including four features')
    for claim in claims:
        if (not claim.get('text') or claim['text'] not in text or not claim.get('fact_ids') or
                not set(claim['fact_ids']) <= set(allowed) | {'title'}):
            raise ValueError('Every copy claim must appear verbatim and reference approved product evidence')
    first_lines = [x.strip() for x in text.splitlines() if x.strip()][:4]
    if any(not any(c['text'] in line for c in claims) for line in first_lines):
        raise ValueError('Every feature line must have a traced claim')
    if version >= 2:
        history = read_json(local_file(root, data.get('selection_history')))
        excluded = check_history(history, root.parent, live=data['mode'] == 'live', fresh=False)
        if product['canonical_url'] in excluded:
            raise ValueError('Selected product was already published or reserved')
        if not copy_review.get('angle') or not copy_review.get('distinct_from_recent'):
            raise ValueError('Explain this product-specific angle and how it differs from recent posts')
        expected_posts = sorted({r['post_url'] for r in history.get('recent_posts', []) if r.get('post_url')})
        if sorted(set(copy_review.get('recent_posts_reviewed', []))) != expected_posts:
            raise ValueError('Review the recent published copies listed in selection history')
        metrics['novelty'] = check_copy_novelty(text, history['records'])
    image_review = review(root, 'image')
    if (image_review.get('panels') != 4 or image_review.get('material_issues') != [] or
            not 1 <= image_review.get('attempt_count', 0) <= 4 or not image_review.get('versions')):
        raise ValueError('Image review must accept four panels without material issues within the retry limit')
    if len(image_review['versions']) != image_review['attempt_count']:
        raise ValueError('Retain every generated attempt in image review')
    if local_file(root, image_review.get('source')) != paths['source_hero'] or local_file(root, image_review.get('final')) != paths['social_image']:
        raise ValueError('Image review must reference this run source and final image')
    image_metrics = validate(paths['social_image'], 'social', 750 * 1024)
    if image_metrics['width'] != image_metrics['height']:
        raise ValueError('Social image must be exactly square')
    if 'social_transport' in paths:
        transport = paths['social_transport']
        validate_transport(transport, (image_metrics['width'], image_metrics['height']))
    files = list(paths.values()) + [local_file(root, f'evidence/{name}-review.json') for name in ['product', 'copy', 'image']]
    files += [local_file(root, version.get('path')) for version in image_review['versions']]
    if data.get('version', 1) >= 2:
        files.append(local_file(root, data['selection_history']))
    hashes = {str(p.relative_to(root)): sha256(p) for p in files}
    return {'status': 'passed', 'validated_at': now(), 'mode': data['mode'], 'product_url': product['canonical_url'],
            'copy': metrics, 'image': image_metrics, 'hashes': hashes}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    args = p.parse_args()
    data = load_manifest(args.manifest)
    if submitted(data):
        raise ValueError('Do not replace validation after submission; use validate_completion.py or reconcile the existing run')
    result = inspect_campaign(args.manifest)
    write_json(args.manifest.parent / 'evidence/campaign-validation.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
