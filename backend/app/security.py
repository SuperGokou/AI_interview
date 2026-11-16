"""Fail-closed admin boundary; candidate/supervisor links remain scoped bearer links."""

import base64
import binascii
import hmac
import os
import re
import time
from collections import deque
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})

# Token-scoped endpoints that candidates / supervisors reach without admin credentials.
_PUBLIC_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"/api/health")),
    ("GET", re.compile(r"/api/sessions/[^/]+")),
    ("POST", re.compile(r"/api/sessions/[^/]+/consent")),
    ("GET", re.compile(r"/api/supervisors/[^/]+(?:/transcripts)?")),
)

# Wrong-password throttle (per client address, in-process).
AUTH_FAILURE_LIMIT = 10
AUTH_FAILURE_WINDOW_S = 300.0
_MAX_TRACKED_CLIENTS = 10_000
_auth_failures: dict[str, deque[float]] = {}

# The SPA is fully self-hosted: scripts, WASM, model and media all come from this origin.
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self' ws: wss:; "
    "worker-src 'self' blob:; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def reset_auth_throttle() -> None:
    """Forget recorded failures (tests, or after rotating the admin password)."""
    _auth_failures.clear()


def _recent_failures(client: str, now: float) -> deque[float]:
    failures = _auth_failures.get(client)
    if failures is None:
        return deque()
    while failures and now - failures[0] > AUTH_FAILURE_WINDOW_S:
        failures.popleft()
    if not failures:
        _auth_failures.pop(client, None)
    return failures


def _record_failure(client: str, now: float) -> None:
    if client not in _auth_failures and len(_auth_failures) >= _MAX_TRACKED_CLIENTS:
        # Bounded memory: drop the oldest tracked client.
        _auth_failures.pop(next(iter(_auth_failures)), None)
    _auth_failures.setdefault(client, deque()).append(now)


def _is_public(method: str, path: str) -> bool:
    return any(method == m and pattern.fullmatch(path) for m, pattern in _PUBLIC_ROUTES)


def _is_protected(path: str) -> bool:
    return (
        path == "/admin"
        or path.startswith("/admin/")
        or path.startswith("/api")
        or path in _DOCS_PATHS
    )


def _credentials_valid(authorization: str, expected_password: str) -> bool:
    try:
        scheme, payload = authorization.split(" ", 1)
        user, password = base64.b64decode(payload, validate=True).decode().split(":", 1)
    except (ValueError, UnicodeError, binascii.Error):
        return False
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    # Evaluate both comparisons so timing does not reveal which half was wrong.
    user_ok = hmac.compare_digest(user.encode(), expected_user.encode())
    password_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return scheme.lower() == "basic" and user_ok and password_ok


def _same_origin(request: Request, origin: str) -> bool:
    """Compare the Origin host with the Host header.

    Scheme is deliberately ignored: behind a TLS-terminating reverse proxy the
    app sees plain http while the browser sends an https Origin.
    """
    host = request.headers.get("host", "").lower()
    return bool(host) and urlsplit(origin).netloc.lower() == host


def _apply_security_headers(response: Response, path: str) -> None:
    if path.startswith("/api") or path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    csp = os.getenv("CONTENT_SECURITY_POLICY", DEFAULT_CSP).strip()
    # Swagger/ReDoc load their UI from a CDN; they are admin-only, so leave them unrestricted.
    if csp and path not in _DOCS_PATHS:
        response.headers.setdefault("Content-Security-Policy", csp)


class AdminBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/")
        denied = self._authorize(request, path)
        response = denied if denied is not None else await call_next(request)
        _apply_security_headers(response, path)
        return response

    @staticmethod
    def _authorize(request: Request, path: str) -> Response | None:
        """Return a denial response, or None when the request may proceed."""
        if not _is_protected(path) or _is_public(request.method, path):
            return None
        expected = os.getenv("ADMIN_PASSWORD", "")
        if not expected:
            return JSONResponse(
                {"detail": "Administrator credentials are not configured"}, status_code=503
            )
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if len(_recent_failures(client, now)) >= AUTH_FAILURE_LIMIT:
            return JSONResponse(
                {"detail": "Too many failed sign-in attempts; try again later"},
                status_code=429,
                headers={"Retry-After": str(int(AUTH_FAILURE_WINDOW_S))},
            )
        authorization = request.headers.get("authorization", "")
        if not _credentials_valid(authorization, expected):
            if authorization:  # a bare first visit is not a guessing attempt
                _record_failure(client, now)
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Kunyao Admin", charset="UTF-8"'},
            )
        origin = request.headers.get("origin")
        if request.method not in _SAFE_METHODS and origin and not _same_origin(request, origin):
            return JSONResponse(
                {"detail": "Cross-origin admin mutation denied"}, status_code=403
            )
        return None
