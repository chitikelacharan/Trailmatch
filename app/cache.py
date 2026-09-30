"""Result cache: Redis when REDIS_URL is set (shared across replicas), otherwise in-process TTL."""
import json, time
from . import config

_r = None
if config.REDIS_URL:
    try:
        import redis
        _r = redis.Redis.from_url(config.REDIS_URL, socket_timeout=1)
        _r.ping()
    except Exception:
        _r = None
_mem = {}


def get(k):
    if _r:
        try:
            v = _r.get(k)
            return json.loads(v) if v else None
        except Exception:
            return None
    v = _mem.get(k)
    if v and v[0] > time.time():
        return v[1]
    _mem.pop(k, None)
    return None


def put(k, val):
    if _r:
        try:
            _r.setex(k, config.CACHE_TTL, json.dumps(val)); return
        except Exception:
            return
    if len(_mem) > 5000:
        _mem.clear()
    _mem[k] = (time.time() + config.CACHE_TTL, val)


def clear():
    _mem.clear()
    if _r:
        try: _r.flushdb()
        except Exception: pass
