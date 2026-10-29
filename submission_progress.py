"""Ephemeral grading progress, shared by web and worker processes.

Only phases and aggregate counts belong here, never test inputs or outputs.
Progress delivery must not affect grading when Redis or the socket is unavailable.
"""
import json
import logging
import uuid

import redis
from config import REDIS_URL


logger = logging.getLogger(__name__)
client = redis.from_url(REDIS_URL, decode_responses=True,
                        socket_connect_timeout=0.2, socket_timeout=0.2)
TTL = 7200
PHASES = {'queued', 'preparing', 'compiling', 'testing'}
_UPDATE = """
local previous = redis.call('GET', KEYS[1])
if not previous or cjson.decode(previous).run_id ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""


def _key(code_id):
    return f'submission:progress:{code_id}'


def _public_progress(value):
    if not isinstance(value, dict) or value.get('phase') not in PHASES:
        return {'phase': 'unknown'}
    result = {'phase': value['phase']}
    completed, total = value.get('completed'), value.get('total')
    if type(completed) is int and type(total) is int and 0 <= completed <= total <= 50 and total > 0:
        result.update(completed=completed, total=total)
    return result


def read_submission_progress(code_id):
    try:
        saved = client.get(_key(code_id))
        return _public_progress(json.loads(saved)) if saved else {'phase': 'queued'}
    except Exception:
        return {'phase': 'unknown'}


def clear_submission_progress(code_id):
    try:
        client.delete(_key(code_id))
    except Exception:
        logger.debug('Could not clear grading progress', exc_info=True)


def start_submission_progress(code_id, emit):
    run_id = uuid.uuid4().hex
    initial = {'phase': 'preparing', 'run_id': run_id}
    cached = True
    try:
        client.setex(_key(code_id), TTL, json.dumps(initial))
    except Exception:
        cached = False

    def progress(phase, completed=None, total=None):
        value = _public_progress(dict(phase=phase, completed=completed, total=total))
        try:
            if cached and not client.eval(_UPDATE, 1, _key(code_id), run_id,
                                          json.dumps(dict(value, run_id=run_id)), TTL):
                return  # A recheck or newer worker has superseded this run.
        except Exception:
            logger.debug('Could not save grading progress', exc_info=True)
        try:
            emit(value)
        except Exception:
            logger.debug('Could not publish grading progress', exc_info=True)

    progress('preparing')
    return progress
