"""Authentication configuration and middleware.

Auth model per SPEC.md §4.2:
- Form-based login page (/login), signed-cookie session (30 day TTL).
- Credentials from env: MENUAPP_USER, MENUAPP_PASSWORD.
- Session signing key from MENUAPP_SESSION_SECRET; generated + warned if unset.
- Dev bypass: if either MENUAPP_USER or MENUAPP_PASSWORD is unset, auth is
  fully disabled and a warning is emitted at startup.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

log = logging.getLogger("menuapp.security")


SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days
SESSION_COOKIE_NAME = "menuapp_session"

# Session signing key resolved once at import. Regenerating per-request would
# invalidate the cookie on every response.
SESSION_SECRET: str
_generated_secret = False
_env_secret = os.environ.get("MENUAPP_SESSION_SECRET")
if _env_secret:
    SESSION_SECRET = _env_secret
else:
    SESSION_SECRET = secrets.token_urlsafe(48)
    _generated_secret = True

HTTPS_ONLY: bool = os.environ.get("MENUAPP_HTTPS_ONLY", "false").lower() == "true"


def get_credentials() -> tuple[str, str] | None:
    """Return (user, password) from env, or None if either is unset (dev bypass)."""
    u = os.environ.get("MENUAPP_USER")
    p = os.environ.get("MENUAPP_PASSWORD")
    if u and p:
        return u, p
    return None


def is_auth_bypassed() -> bool:
    return get_credentials() is None


def _hash(s: str) -> bytes:
    return hashlib.sha256(s.encode("utf-8")).digest()


def verify_credentials(username: str, password: str) -> bool:
    creds = get_credentials()
    if creds is None:
        return True
    # Hash both sides so secrets.compare_digest works for non-ASCII and any
    # length input (avoiding the ASCII-only restriction of string compare).
    return secrets.compare_digest(_hash(username), _hash(creds[0])) and secrets.compare_digest(
        _hash(password), _hash(creds[1])
    )


def safe_next(next_url: str | None) -> str:
    """Only allow relative paths starting with '/'. Prevents open-redirects."""
    if not next_url:
        return "/"
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


PUBLIC_PATH_EXACT: set[str] = {"/login", "/logout", "/healthz"}
PUBLIC_PATH_PREFIXES: tuple[str, ...] = ("/static/",)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATH_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_public(request.url.path):
            return await call_next(request)
        if is_auth_bypassed():
            return await call_next(request)
        if request.session.get("user"):
            return await call_next(request)
        next_url = request.url.path
        if request.url.query:
            next_url += "?" + request.url.query
        return RedirectResponse(
            url=f"/login?next={quote(next_url, safe='')}", status_code=303
        )


def log_startup_warnings() -> None:
    if is_auth_bypassed():
        log.warning(
            "MENUAPP_USER/MENUAPP_PASSWORD not set — auth is BYPASSED (dev mode)."
        )
    if _generated_secret:
        log.warning(
            "MENUAPP_SESSION_SECRET not set — using a random key. "
            "Sessions will not survive a process restart."
        )
