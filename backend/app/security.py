"""Fail-closed admin boundary; candidate/supervisor links remain scoped bearer links."""
import base64
import binascii
import hmac
import os
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class AdminBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path.rstrip('/')
        public = (
            path == '/api/health'
            or (request.method == 'GET' and re.fullmatch(r'/api/sessions/[^/]+', path))
            or (request.method == 'POST' and re.fullmatch(r'/api/sessions/[^/]+/consent', path))
            or (request.method == 'GET' and re.fullmatch(r'/api/supervisors/[^/]+(?:/transcripts)?', path))
        )
        protected = path == '/admin' or path.startswith('/admin/') or path.startswith('/api') or path in ('/docs', '/redoc', '/openapi.json')
        if protected and not public:
            expected = os.getenv('ADMIN_PASSWORD', '')
            if not expected:
                return JSONResponse({'detail': 'Administrator credentials are not configured'}, status_code=503)
            valid = False
            try:
                scheme, payload = request.headers.get('authorization', '').split(' ', 1)
                user, password = base64.b64decode(payload, validate=True).decode().split(':', 1)
                valid = scheme.lower() == 'basic' and hmac.compare_digest(user.encode(), os.getenv('ADMIN_USERNAME', 'admin').encode()) and hmac.compare_digest(password.encode(), expected.encode())
            except (ValueError, UnicodeError, binascii.Error):
                pass
            if not valid:
                return JSONResponse({'detail': 'Authentication required'}, status_code=401, headers={'WWW-Authenticate': 'Basic realm="Kunyao Admin", charset="UTF-8"'})
            origin = request.headers.get('origin')
            if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail': 'Cross-origin admin mutation denied'}, status_code=403)
        response = await call_next(request)
        if path.startswith('/api') or path.startswith('/admin'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response
