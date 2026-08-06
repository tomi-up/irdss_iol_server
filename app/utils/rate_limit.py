"""
Gateway-wide rate limiting (slowapi / limits, in-memory — same storage philosophy
as app.utils.request_log: no external dependency, resets on restart, fine at this
project's scale).

Keyed by the caller's X-API-Key rather than remote address wherever possible: every
hospital and every admin proxies through the mock_hospitals PHP server, which makes
its own server-side cURL calls to this gateway. FastAPI only ever sees that one PHP
process's IP as the remote address, so IP-based keying would lump every hospital and
the admin panel into a single shared bucket. Keying by (a hash of) the credential
itself gives each hospital/admin their own independent quota instead.
"""

import hashlib

from fastapi import Request
from limits import parse
from slowapi import Limiter
from slowapi.util import get_remote_address

DEFAULT_LIMIT = "300/minute"


def key_by_api_key_or_ip(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return "key:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return "ip:" + get_remote_address(request)


limiter = Limiter(key_func=key_by_api_key_or_ip, default_limits=[DEFAULT_LIMIT])

# slowapi's bundled SlowAPIMiddleware auto-detects each route's handler by walking
# app.routes — that breaks under this project's FastAPI version, which wraps routes
# registered via app.include_router in an internal _IncludedRouter object instead of
# exposing them as top-level Route entries. The middleware silently treats every
# such route as exempt, so the default limit never actually fires. Parsed once here
# and enforced manually in main.py's own middleware instead, bypassing that broken
# lookup entirely. The per-route @limiter.limit(...) decorators (see admin_auth.py)
# are unaffected — they wrap the endpoint function directly and never go through it.
DEFAULT_LIMIT_ITEM = parse(DEFAULT_LIMIT)
