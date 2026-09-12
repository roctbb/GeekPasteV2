"""Repair one verified GitHub pair. Dry run by default; never regrade or notify teachers."""
import argparse
import hashlib
import json
import os

import requests
from sqlalchemy import or_

from manage import app
from models import Code, db, similarities_table
from config import APP_URL, SUBMIT_URL, SIMILARITY_LEVEL, MAX_SIMILARITY_CODE_SIZE
from github_similarity import prepare_github_source, source_similarity
from methods import build_academic_integrity_payload, generate_jwt


def repair_pair(first_id, second_id, apply=False, backup=None):
    if first_id == second_id:
        raise ValueError('Two different submissions are required')
    codes = [Code.query.filter_by(id=cid).one() for cid in (first_id, second_id)]
    a, b = codes
    if any(c.lang != 'github' for c in codes) or a.user_id == b.user_id or (a.task_id, a.course_id) != (b.task_id, b.course_id):
        raise ValueError('Pair is outside the GitHub similarity scope')
    sources = [prepare_github_source(c.code, MAX_SIMILARITY_CODE_SIZE) for c in codes]
    percent = source_similarity(*sources)
    pair_filter = or_(
        (similarities_table.c.code_id == a.id) & (similarities_table.c.code_id2 == b.id),
        (similarities_table.c.code_id == b.id) & (similarities_table.c.code_id2 == a.id))
    rows = [dict(row._mapping) for row in db.session.execute(similarities_table.select().where(pair_filter))]
    snapshot = {'pair': rows, 'new_percent': percent, 'codes': [{
        'id': c.id, 'source_sha256': hashlib.sha256(c.code.encode()).hexdigest(),
        'similarity_checked': c.similarity_checked, 'has_similarity_warning': c.has_similarity_warning,
        'has_critical_similarity_warning': c.has_critical_similarity_warning,
        'check_points': c.check_points, 'check_state': c.check_state,
    } for c in codes]}
    print(json.dumps(snapshot, ensure_ascii=False))
    if not apply:
        return snapshot
    if not backup:
        raise ValueError('--backup is required with --apply')
    # Exclusive private backup before any mutation; accidental reruns cannot overwrite it.
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(snapshot, output, ensure_ascii=False, indent=2)
    locked = Code.query.filter(Code.id.in_([a.id, b.id])).order_by(Code.id).with_for_update().populate_existing().all()
    for c in locked:
        old = next(item for item in snapshot['codes'] if item['id'] == c.id)
        if hashlib.sha256(c.code.encode()).hexdigest() != old['source_sha256']:
            raise RuntimeError('Submission changed during comparison; abort and retry')
    db.session.execute(similarities_table.delete().where(pair_filter))
    if percent >= SIMILARITY_LEVEL:
        db.session.execute(similarities_table.insert().values(code_id=a.id, code_id2=b.id, percent=percent))
    for c in locked:
        remaining = db.session.execute(similarities_table.select().where(or_(
            similarities_table.c.code_id == c.id, similarities_table.c.code_id2 == c.id))).fetchall()
        c.has_similarity_warning = any(row.percent >= SIMILARITY_LEVEL for row in remaining)
        c.has_critical_similarity_warning = any(row.percent > 95 for row in remaining)
        c.similarity_checked = True
    db.session.commit()
    return snapshot


def sync_flags(code_ids):
    for cid in code_ids:
        c = Code.query.filter_by(id=cid).one()
        response = requests.post(SUBMIT_URL.rstrip('/') + '/integrity', json={
            'solution': APP_URL + f'/?id={c.id}', 'course_id': c.course_id,
            'token': generate_jwt(c.user_id, c.task_id),
            'academic_integrity': build_academic_integrity_payload(c),
        }, timeout=(3, 15))
        response.raise_for_status()
        if response.json().get('state') != 'ok':
            raise RuntimeError(f'CodingProjects did not confirm integrity sync for {cid}')
        print(f'Integrity synced: {cid}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first')
    parser.add_argument('second')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup')
    parser.add_argument('--sync-only', action='store_true', help='Retry the read-only-for-grades integrity callback')
    args = parser.parse_args()
    with app.app_context():
        if not args.sync_only:
            repair_pair(args.first, args.second, args.apply, args.backup)
        if args.apply or args.sync_only:
            sync_flags([args.first, args.second])
