#!/usr/bin/env python3
"""Validate Delan Facebook copy, reviewed evidence and social assets; save hashes."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from PIL import Image
from common import load_manifest, local_file, now, read_json, sha256, submitted, timestamp, write_json
from optimize_image import validate

WORD = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
TAG = re.compile(r'#[A-Za-z][A-Za-z0-9_]*')
EMOJI = ('🏭', '📦', '🛠', '⚙', '🔧', '✅', '💡', '📏', '🔌', '⚡', '🧵', '🛡', '🔗', '🔬', '🤖', '🔄')


def validate_copy(text, url):
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 8 or not all(line.startswith(EMOJI) for line in lines[:4]):
        raise ValueError('Start with exactly four emoji feature lines, then benefit, CTA, URL, hashtags')
    if any(line.startswith(EMOJI) for line in lines[4:]):
        raise ValueError('Only four feature lines are allowed')
    if lines[-2] != url or re.findall(r'https?://\S+', text) != [url]:
        raise ValueError('The sole URL must be the selected product link on the penultimate nonempty line')
    tags = TAG.findall(lines[-1])
    if not 8 <= len(tags) <= 12 or len(set(t.casefold() for t in tags)) != len(tags) or TAG.sub('', lines[-1]).strip():
        raise ValueError('Last line must contain 8–12 unique English hashtags')
    if TAG.search('\n'.join(lines[:-1])):
        raise ValueError('Keep all hashtags on the final line')
    words = len(WORD.findall('\n'.join(lines[:-2])))
    if not 80 <= words <= 150 or re.search(r'[\u3400-\u9fff]', text):
        raise ValueError(f'Copy must have 80–150 English body words, excluding URL/hashtags; found {words}')
    return {'body_words': words, 'feature_lines': 4, 'hashtags': len(tags)}


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
    metrics = validate_copy(text, product['canonical_url'])
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
        with Image.open(transport) as im:
            im.verify()
        with Image.open(transport) as im:
            if im.format != 'JPEG' or im.size != (image_metrics['width'], image_metrics['height']) or im.getexif() or any(k in im.info for k in ['exif', 'xmp', 'icc_profile', 'comment']):
                raise ValueError('Transport must be metadata-free JPEG with canonical image dimensions')
        if transport.stat().st_size > 750 * 1024:
            raise ValueError('Transport exceeds 750 KiB')
    files = list(paths.values()) + [local_file(root, f'evidence/{name}-review.json') for name in ['product', 'copy', 'image']]
    files += [local_file(root, version.get('path')) for version in image_review['versions']]
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
