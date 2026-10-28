#!/usr/bin/env python3
"""Record Facebook-only state; require frozen validation before every submit."""
from __future__ import annotations
import argparse
import copy
import fcntl
import json
import sys
from pathlib import Path
from common import (check_target_evidence, checked_hashes, checked_publication, load_manifest,
                    local_file, now, read_json, recent, submitted, timestamp, write_json)
from validate_campaign import inspect_campaign
from publication_history import guard_submission

STATUSES = {'pending', 'published', 'blocked', 'failed', 'uncertain'}


def update(path, status, url=None, error=None, submission_started=False, evidence=None, reconciliation=None):
    path = Path(path).resolve()
    if status not in STATUSES:
        raise ValueError('Unsupported Facebook status')
    # Serialize all runs sharing this history root, not merely updates to one manifest.
    with (path.parent.parent / '.publication.lock').open('a') as root_lock, path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(root_lock, fcntl.LOCK_EX)
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load_manifest(path)
        root = path.parent
        channel = data['channels']['facebook']
        if data.get('status') == 'rejected':
            raise ValueError('This product was rejected and cannot be submitted')
        if channel['status'] == 'published':
            raise ValueError('Already published; verify completion instead of updating or republishing')
        if (submission_started or status == 'published') and data['mode'] != 'live':
            raise ValueError('Dry runs cannot submit or claim publication')
        if status == 'uncertain' and not submitted(data):
            raise ValueError('Uncertain is only for a started submission')
        event = {'status': status, 'at': now()}
        if error:
            event['error'] = str(error)[:2000]
        if submission_started:
            if status != 'pending':
                raise ValueError('Use pending when recording the start of submission')
            preflight = read_json(local_file(root, 'evidence/preflight.json'))
            check_target_evidence(root, preflight)
            recent(preflight.get('checked_at', ''))
            if preflight.get('identity_confirmed') is not True or preflight.get('can_create_post') is not True or not preflight.get('active_identity'):
                raise ValueError('Current target identity and posting permission must be confirmed')
            prior = [e for e in data.get('history', []) if e.get('submission_started_at')]
            if len(prior) >= 2:
                raise ValueError('At most one reconciled retry is allowed')
            if submitted(data) and not prior:
                raise ValueError('Submission history is inconsistent; do not retry')
            if not prior or data.get('version', 1) >= 2:
                event['duplicate_guard'] = guard_submission(path, data, preflight)
            if prior:
                if not reconciliation:
                    raise ValueError('Reconcile the first submission before a single bounded retry')
                reconcile_path = local_file(root, str(reconciliation))
                rec = read_json(reconcile_path)
                check_target_evidence(root, rec)
                recent(rec.get('checked_at', ''))
                if (rec.get('confirmed_absent') is not True or rec.get('no_pending_submission') is not True or not rec.get('notes') or
                        timestamp(rec['checked_at']) <= timestamp(prior[-1]['submission_started_at'])):
                    raise ValueError('Fresh evidence must show no published or pending submission')
                event['reconciliation'] = copy.deepcopy(rec)
                report = prior[0]['validation']
            else:
                report = read_json(local_file(root, 'evidence/campaign-validation.json'))
            checked_hashes(root, report)
            current = inspect_campaign(path)
            if current['hashes'] != report['hashes']:
                raise ValueError('Campaign evidence has changed since validation')
            event.update(submission_started_at=now(), validation=copy.deepcopy(report), preflight=copy.deepcopy(preflight))
            data.setdefault('submission_started_at', event['submission_started_at'])
            data['submission_count'] = len(prior) + 1
        elif reconciliation:
            raise ValueError('--reconciliation is only for a submission retry')
        if status == 'published':
            if not submitted(data) or not url or not evidence:
                raise ValueError('Published requires submission history, URL and public verification evidence')
            publication = checked_publication(root, data, url, evidence)
            event.update(url=url, evidence=str(local_file(root, str(evidence)).relative_to(root)), publication=publication)
        elif url or evidence:
            raise ValueError('URL and publication evidence are only for published status')
        channel.update(event)
        if status != 'published' and not error:
            channel.pop('error', None)
        data.setdefault('history', []).append(copy.deepcopy(event))
        data.update(status='publishing' if submission_started else status, updated_at=now())
        write_json(path, data)
        return {'manifest': str(path), 'status': data['status'], 'submission_count': data.get('submission_count', 0)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--status', choices=sorted(STATUSES), required=True)
    p.add_argument('--url')
    p.add_argument('--error')
    p.add_argument('--submission-started', action='store_true')
    p.add_argument('--evidence')
    p.add_argument('--reconciliation')
    a = p.parse_args()
    print(json.dumps(update(a.manifest, a.status, a.url, a.error, a.submission_started, a.evidence, a.reconciliation), indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
