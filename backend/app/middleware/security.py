from __future__ import annotations

import re
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class InputSanitizer:
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_QUERY_LENGTH = 500
    MAX_PATH_LENGTH = 200
    SUSPICIOUS_PATTERNS = [
        re.compile(r'<script[^>]*>', re.IGNORECASE),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'on\w+\s*=', re.IGNORECASE),
        re.compile(r'union\s+select', re.IGNORECASE),
        re.compile(r';\s*drop\s+table', re.IGNORECASE),
        re.compile(r'\.\./\.\./'),
    ]

    @classmethod
    def check_request(cls, request: Request) -> str | None:
        path = request.url.path
        if len(path) > cls.MAX_PATH_LENGTH:
            return "path_too_long"
        for key, values in request.query_params.multi_items():
            if len(key) > 100 or len(values) > cls.MAX_QUERY_LENGTH:
                return "query_too_long"
            for pattern in cls.SUSPICIOUS_PATTERNS:
                if pattern.search(values):
                    return "suspicious_input"
        return None


class FileUploadGuard:
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
    ALLOWED_TYPES = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".pptx"}
    DANGEROUS_SIGNATURES = [
        b'\x4d\x5a',  # PE/EXE
        b'\x7f\x45\x4c\x46',  # ELF
        b'\x23\x21',  # Shell script #!
    ]

    @classmethod
    def validate_upload(cls, filename: str, content: bytes) -> str | None:
        if len(content) > cls.MAX_FILE_SIZE:
            return "file_too_large"
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in cls.ALLOWED_TYPES:
            return "file_type_not_allowed"
        for sig in cls.DANGEROUS_SIGNATURES:
            if content[:len(sig)] == sig:
                return "dangerous_file_type"
        return None


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        with self._lock:
            reqs = self._requests[client_id]
            cutoff = now - self.window
            self._requests[client_id] = [t for t in reqs if t > cutoff]
            if len(self._requests[client_id]) >= self.max_requests:
                return False
            self._requests[client_id].append(now)
            return True


rate_limiter = RateLimiter(max_requests=60, window_seconds=60)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(client_ip):
            return Response(content='{"code":429,"message":"rate_limit_exceeded"}', status_code=429, media_type="application/json")

        error = InputSanitizer.check_request(request)
        if error:
            return Response(content=f'{{"code":400,"message":"{error}"}}', status_code=400, media_type="application/json")

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
