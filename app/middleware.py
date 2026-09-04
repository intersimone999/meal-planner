"""ASGI middleware helpers."""

from __future__ import annotations

from typing import Awaitable, Callable

Scope = dict
Message = dict
Send = Callable[[Message], Awaitable[None]]
Receive = Callable[[], Awaitable[Message]]


class StripRootPathMiddleware:
    """Strip a leaked `root_path` prefix from the incoming request path.

    Some reverse-proxy configurations (Apache's `ProxyPass … nocanon`,
    for instance) forward the ORIGINAL URL to the backend instead of the
    prefix-stripped version. When uvicorn also runs with --root-path, the
    backend then sees a request whose `scope['path']` still contains the
    mount prefix — routes registered as `/login` never match against a
    literal `/meal-planner/login`, and AuthMiddleware treats /meal-planner/
    /login as private and redirects into a loop.

    This middleware runs OUTERMOST on incoming ASGI scopes. When
    `scope['path']` starts with `scope['root_path']`, strip the prefix
    once so every layer below (auth, routing, templates' url_for) sees
    a clean app-relative path.

    No-op when root_path is empty or already stripped by the proxy.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            root_path = scope.get("root_path", "")
            path = scope.get("path", "")
            if root_path and path.startswith(root_path):
                new_path = path[len(root_path):] or "/"
                scope = dict(scope)  # avoid mutating a shared scope
                scope["path"] = new_path
                raw = scope.get("raw_path")
                if isinstance(raw, bytes):
                    prefix_b = root_path.encode("ascii")
                    if raw.startswith(prefix_b):
                        scope["raw_path"] = raw[len(prefix_b):] or b"/"
        await self.app(scope, receive, send)


class LocationHeaderRootPathMiddleware:
    """Prefix outgoing `Location` headers with the ASGI scope's `root_path`.

    When Meal Planner runs behind a reverse-proxy sub-path (e.g. Apache
    proxying `/meal-planner/*` to the app's `/*`), any redirect the app
    emits with an origin-relative path like `/login` would send the
    browser to `http://host/login` — outside the sub-path — breaking the
    proxy contract.

    This middleware inspects `Location` headers on responses; if the
    header starts with `/` (origin-relative), is not protocol-relative
    (`//`), and isn't already root_path-prefixed, it prepends root_path.

    No-op when root_path is empty (dev + tests).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        root_path = scope.get("root_path", "")
        if scope["type"] != "http" or not root_path:
            return await self.app(scope, receive, send)
        prefix = root_path.encode("ascii")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                new_headers = []
                for name, value in message.get("headers", []):
                    if (
                        name.lower() == b"location"
                        and value.startswith(b"/")
                        and not value.startswith(b"//")
                        and not value.startswith(prefix + b"/")
                        and value != prefix
                    ):
                        value = prefix + value
                    new_headers.append((name, value))
                message["headers"] = new_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
