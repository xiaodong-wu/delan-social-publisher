#!/usr/bin/env python3
"""Plan and verify Google Sheets reporting; external reads/writes use the Sheets connector."""
from __future__ import annotations
import argparse
import copy
import fcntl
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from common import checked_publication, load_manifest, local_file, now, read_json, sha256, timestamp, write_json

SPREADSHEET_ID = '18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid=0'
SHEET_TITLE = '工作表1'
HEADERS = ['域名', '发布时间', '发布的站内链接', 'Facebook链接', 'LinkedIn链接']


def plan(path):
    path = Path(path).resolve()
    data = load_manifest(path)
    fb = data['channels']['facebook']
    if data['mode'] != 'live' or fb['status'] != 'published':
        raise ValueError('Reporting requires a verified live Facebook publication')
    publication = checked_publication(path.parent, data, fb.get('url', ''), fb.get('evidence', ''))
    published_at = timestamp(publication['verified_at']).astimezone(ZoneInfo('Asia/Shanghai'))
    return {'spreadsheet_id': SPREADSHEET_ID, 'sheet_title': SHEET_TITLE, 'sheet_id': 0,
            'headers': HEADERS, 'dedupe_key': fb['url'], 'url': SHEET_URL,
            'values': ['en.delancable.com', published_at.strftime('%Y-%m-%d %H:%M:%S'),
                       '不适用', fb['url'], '不适用'],
            'time_source': 'facebook_publication_verified_at'}


def cell_values(readback, row_index):
    """Extract five exact literal strings from a bounded get_spreadsheet_cells result."""
    sheets = [s for s in readback.get('sheets', [])
              if s.get('properties', {}).get('sheetId') == 0 and s['properties'].get('title') == SHEET_TITLE]
    if len(sheets) != 1:
        raise ValueError('Reporting readback must identify the expected sheet')
    for grid in sheets[0].get('data', []):
        offset = row_index - grid.get('startRow', 0)
        rows = grid.get('rowData', [])
        if grid.get('startColumn', 0) == 0 and 0 <= offset < len(rows):
            return [c.get('userEnteredValue', {}).get('stringValue') for c in rows[offset].get('values', [])[:5]]
    raise ValueError('Readback does not contain the required row')


def checked_reporting(path, evidence_path):
    path = Path(path).resolve()
    expected = plan(path)
    evidence_file = local_file(path.parent, str(evidence_path))
    evidence = read_json(evidence_file)
    verified = timestamp(evidence.get('verified_at', ''))
    fb_verified = timestamp(load_manifest(path)['channels']['facebook']['publication']['verified_at'])
    if verified < fb_verified:
        raise ValueError('Reporting evidence predates publication verification')
    readback = evidence.get('readback', {})
    if readback.get('spreadsheetId') != SPREADSHEET_ID or readback.get('properties', {}).get('title') != 'social-auto-upload':
        raise ValueError('Wrong reporting spreadsheet')
    row = evidence.get('row_number')
    if type(row) is not int or row < 2:
        raise ValueError('Reporting requires the verified data row number')
    if cell_values(readback, 0) != HEADERS or cell_values(readback, row - 1) != expected['values']:
        raise ValueError('Reporting headers or row values do not match the publication')
    search = evidence.get('search', {})
    if (search.get('matched_row_count') != 1 or search.get('returned_matching_row_count') != 1 or
            any(search.get(k) for k in ['truncated', 'truncated_rows', 'truncated_columns'])):
        raise ValueError('Reporting must have exactly one fully returned matching row')
    bounds = re.fullmatch(r"(?:'?工作表1'?!)?A1:E(\d+)", search.get('scanned_range', ''))
    grid_rows = readback['sheets'][0]['properties']['gridProperties']['rowCount']
    if not bounds or int(bounds[1]) != grid_rows:
        raise ValueError('Dedupe search must cover the current bounded A:E data grid')
    matching_rows = [line.split('|')[1:-1] for line in search.get('markdown', '').splitlines()
                     if expected['dedupe_key'] in line]
    if len(matching_rows) != 1 or [v.strip() for v in matching_rows[0]] != [str(row)] + expected['values']:
        raise ValueError('Search evidence must match the exact recorded row and all five values')
    return {'status': 'reported', 'verified_at': evidence['verified_at'], 'url': SHEET_URL,
            'spreadsheet_id': SPREADSHEET_ID, 'sheet_title': SHEET_TITLE, 'sheet_id': 0,
            'row_number': row, 'range': f"'{SHEET_TITLE}'!A{row}:E{row}",
            'values': expected['values'], 'dedupe_key': expected['dedupe_key'],
            'evidence': str(evidence_file.relative_to(path.parent)), 'evidence_sha256': sha256(evidence_file)}


def record(path, status, evidence=None, error=None):
    path = Path(path).resolve()
    if status not in {'reported', 'blocked', 'failed', 'uncertain'}:
        raise ValueError('Unsupported reporting status')
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        plan(path)
        data = load_manifest(path)
        previous = data.get('reporting', {}).get('google_sheet', {})
        if previous.get('status') == 'reported':
            checked = checked_reporting(path, previous.get('evidence', ''))
            if status != 'reported' or checked != previous:
                raise ValueError('Reported rows cannot be downgraded or silently replaced')
            return previous
        if status == 'reported':
            result = checked_reporting(path, evidence)
        else:
            if not error:
                raise ValueError('An incomplete reporting result requires an error')
            result = {'status': status, 'at': now(), 'error': str(error)[:2000], 'url': SHEET_URL}
        data.setdefault('reporting', {})['google_sheet'] = result
        data.setdefault('reporting_history', []).append(copy.deepcopy(result))
        data.update(status='reporting_pending', updated_at=now())
        data.pop('completion', None)
        write_json(path, data)
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--plan', action='store_true')
    p.add_argument('--status', choices=['reported', 'blocked', 'failed', 'uncertain'])
    p.add_argument('--evidence')
    p.add_argument('--error')
    a = p.parse_args()
    if a.plan:
        result = plan(a.manifest)
    elif a.status:
        result = record(a.manifest, a.status, a.evidence, a.error)
    else:
        p.error('Choose --plan or --status')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
