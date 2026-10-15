"""Shared local state and evidence checks for the Delan Facebook workflow."""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TARGET_URL = 'https://www.facebook.com/dlflexdelancable'
CATALOG_URL = 'https://en.delancable.com/product'
SKILL = 'delan-social-publisher'


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return data


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.' + path.name, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        temp = f.name
    os.replace(temp, path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_file(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing local artifact path')
    path = (root / value).resolve()
    if root.resolve() not in path.parents or not path.is_file() or not path.stat().st_size:
        raise ValueError(f'Artifact must be a nonempty file inside run: {value}')
    return path


def load_manifest(path):
    data = read_json(path)
    if (data.get('skill') != SKILL or data.get('target_url') != TARGET_URL or
            set(data.get('channels', {})) != {'facebook'} or data.get('mode') not in {'live', 'dry-run'}):
        raise ValueError('Manifest must belong to this Facebook-only Delan skill')
    return data


def submitted(data):
    return bool(data.get('submission_started_at') or
                data['channels']['facebook'].get('status') in {'published', 'uncertain'} or
                any(e.get('submission_started_at') for e in data.get('history', [])))


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must have a timezone')
    return dt


def recent(value, minutes=30):
    age = (datetime.now(timezone.utc) - timestamp(value)).total_seconds()
    if not -60 <= age <= minutes * 60:
        raise ValueError('Evidence timestamp is stale or in the future')


def check_target_evidence(root, data):
    if data.get('target_url') != TARGET_URL:
        raise ValueError('Evidence target is not the Delan Facebook page')
    local_file(root, data.get('evidence_file'))


def validate_permalink(url, page_id=''):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in {'facebook.com', 'www.facebook.com', 'm.facebook.com'} or p.username or p.password or p.port not in {None, 443}:
        raise ValueError('Not a Facebook HTTPS permalink')
    m = re.fullmatch(r'/([^/]+)/posts/([^/]+)/?', p.path)
    if m and (m[1].lower() == 'dlflexdelancable' or (page_id.isdigit() and m[1] == page_id)):
        return
    q = parse_qs(p.query)
    if p.path in {'/permalink.php', '/story.php'} and q.get('story_fbid') and page_id.isdigit() and q.get('id') == [page_id]:
        return
    raise ValueError('Permalink must identify the verified Delan page and an individual post')


def checked_publication(root, manifest, url, evidence_path):
    data = read_json(local_file(root, str(evidence_path)))
    check_target_evidence(root, data)
    attempts = [e for e in manifest.get('history', []) if e.get('submission_started_at')]
    if not attempts:
        raise ValueError('Publication requires a saved submission event')
    preflight = attempts[-1]['preflight']
    validate_permalink(url, str(preflight.get('observed_page_id', '')))
    if data.get('post_url') != url or not data.get('notes'):
        raise ValueError('Publication evidence must match the exact post URL and include notes')
    if any(data.get(k) is not True for k in ['author_matches', 'text_matches', 'product_link_matches', 'image_matches']):
        raise ValueError('Publication has not been fully verified')
    verified = timestamp(data.get('verified_at', ''))
    if verified < timestamp(manifest['submission_started_at']):
        raise ValueError('Publication evidence predates submission')
    if (verified - datetime.now(timezone.utc)).total_seconds() > 60:
        raise ValueError('Publication evidence is dated in the future')
    return data


def checked_hashes(root, report, allow_missing_transport=False):
    if report.get('status') != 'passed' or not report.get('hashes'):
        raise ValueError('A passing campaign validation is required')
    for name, digest in report['hashes'].items():
        if allow_missing_transport and name == 'social-upload.jpg' and not (root / name).exists():
            continue
        if sha256(local_file(root, name)) != digest:
            raise ValueError(f'Artifact changed since validation/submission: {name}')
