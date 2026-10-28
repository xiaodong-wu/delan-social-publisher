#!/usr/bin/env python3
"""Require verified Facebook publication and an exact, deduplicated Google Sheets audit row."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from common import checked_hashes, checked_publication, load_manifest, local_file, now, sha256, write_json
from validate_campaign import inspect_campaign
from record_reporting import checked_reporting


def complete(path):
    path = Path(path).resolve()
    data, root = load_manifest(path), path.parent
    channel = data['channels']['facebook']
    if data['mode'] != 'live' or channel['status'] != 'published' or not data.get('submission_started_at'):
        raise ValueError('Only a verified live Facebook publication can complete')
    attempts = [e for e in data.get('history', []) if e.get('submission_started_at')]
    if not 1 <= len(attempts) <= 2 or len(attempts) != data.get('submission_count'):
        raise ValueError('Missing or inconsistent submission history')
    frozen = attempts[0]['validation']
    if data.get('version', 1) >= 2:
        guard = attempts[-1].get('duplicate_guard', {})
        if guard.get('history_sha256') != sha256(local_file(root, 'evidence/history-preflight.json')):
            raise ValueError('Submission history preflight is missing or changed')
    checked_hashes(root, frozen, allow_missing_transport=True)
    current = inspect_campaign(path, allow_missing_transport=True)
    for name, digest in current['hashes'].items():
        if frozen['hashes'].get(name) != digest:
            raise ValueError('Campaign differs from submitted artifacts')
    checked_publication(root, data, channel.get('url', ''), channel.get('evidence', ''))
    reporting = data.get('reporting', {}).get('google_sheet', {})
    if reporting.get('status') != 'reported':
        raise ValueError('Facebook is published, but Google Sheets reporting is not verified')
    if checked_reporting(path, reporting.get('evidence', '')) != reporting:
        raise ValueError('Google Sheets reporting differs from its verified evidence')
    result = {'status': 'complete', 'verified_at': now(), 'facebook_url': channel['url'],
              'product_url': data['product']['canonical_url'], 'manifest': str(path),
              'google_sheet_url': reporting['url'], 'google_sheet_row': reporting['row_number']}
    write_json(root / 'evidence/completion-validation.json', result)
    data['status'] = 'complete'
    data['completion'] = result
    write_json(path, data)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    args = p.parse_args()
    print(json.dumps(complete(args.manifest), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
