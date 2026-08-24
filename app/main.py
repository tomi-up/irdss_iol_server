import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.cors import CORSMiddleware

from app.routers import admin, admin_auth, referral, hospitals
from app.utils.rate_limit import DEFAULT_LIMIT_ITEM, key_by_api_key_or_ip, limiter
from app.utils.request_log import record_request

# Initialize the FastAPI application gateway
app = FastAPI(
    title="IRDSS Interoperability Layer API",
    description="API Gateway for the Mindanao-wide Intelligent Referral Decision Support System.",
    version="1.0.0"
)
origins = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:80",
    "http://127.0.0.1:80",
    "http://localhost:63343",  # Your IDE preview port if you use it
    "http://localhost:5173",   # Vite dev server for the Admin Panel
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # " * " allows ANY frontend origin to call your FastAPI backend cleanly!
    allow_credentials=True,
    allow_methods=["*"],  # Allows GET, POST, PATCH, OPTIONS, etc.
    allow_headers=["*"],  # Allows X-API-Key, Content-Type, etc.
)

# Rate limiting (slowapi). See app/utils/rate_limit.py for why the default limit is
# enforced manually below rather than via slowapi's own SlowAPIMiddleware — its
# automatic route detection doesn't work with this project's FastAPI version. The
# stricter per-route limits on admin login/2FA (app/routers/admin_auth.py) still use
# the normal @limiter.limit(...) decorator, which is unaffected by that issue.
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Matches this gateway's normal {"detail": ...} error shape instead of slowapi's default."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Slow down and try again shortly."},
    )


@app.middleware("http")
async def enforce_default_rate_limit(request: Request, call_next):
    """Global per-credential cap applied to every endpoint (see app/utils/rate_limit.py)."""
    key = key_by_api_key_or_ip(request)
    if not limiter.limiter.hit(DEFAULT_LIMIT_ITEM, key):
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Rate limit exceeded: {DEFAULT_LIMIT_ITEM}. Slow down and try again shortly."
            },
        )
    return await call_next(request)


# Polling these from the Monitoring page's own auto-refresh would otherwise write
# entries about themselves into the very buffer they're displaying, crowding out
# real hospital/referral traffic purely by being the most frequent caller. The
# DELETE (flush) on /system/logs is a deliberate, infrequent admin action, not
# passive polling, so it's still logged.
_UNLOGGED_GET_PATHS = {"/api/v1/admin/system/health", "/api/v1/admin/system/logs"}


@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    """
    Records every completed request into the in-memory monitoring buffer that powers
    the Admin Panel's server-log viewer. Never swallows the underlying exception:
    failures are logged as HTTP 500 entries and then re-raised untouched.
    """
    if request.method == "GET" and request.url.path in _UNLOGGED_GET_PATHS:
        return await call_next(request)

    started = time.perf_counter()
    client_ip = request.client.host if request.client else None

    try:
        response = await call_next(request)
    except Exception as exc:
        record_request(
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=(time.perf_counter() - started) * 1000,
            client_ip=client_ip,
            hospital_name=getattr(request.state, "hospital_name", None),
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    record_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=(time.perf_counter() - started) * 1000,
        client_ip=client_ip,
        # Populated by the API-key dependencies once they resolve the caller's identity
        hospital_name=getattr(request.state, "hospital_name", None),
    )
    return response


from fastapi.staticfiles import StaticFiles
import os

from app.routers import admin, admin_auth, referral, hospitals, facility_auth, assessments, ws

# Ensure storage directory exists for LTO file uploads
os.makedirs("storage/lto_files", exist_ok=True)
app.mount("/storage/lto_files", StaticFiles(directory="storage/lto_files"), name="lto_files")

# Register all application route modules
app.include_router(admin.router)
app.include_router(admin_auth.router)
app.include_router(facility_auth.router)
app.include_router(referral.router)
app.include_router(hospitals.router)
app.include_router(assessments.router)
app.include_router(ws.router)


# Register the internal SYSTEM_ADMIN control plane consumed by admin_frontend.
# admin_auth (login/2fa) is intentionally registered separately from admin —
# it has no verify_admin_key dependency, since it's what establishes the session.
app.include_router(admin_auth.router)
app.include_router(admin.router)

# A simple health-check endpoint to verify the server is running
@app.get("/")
async def root():
    return {"message": "Welcome to the IRDSS Interoperability Layer API. The server is live and secure."}

