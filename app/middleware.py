"""ASGI middleware helpers."""

from __future__ import annotations

from typing import Awaitable, Callable

Scope = dict
Message = dict
Send = Callable[[Message], Awaitable[None]]
Receive = Callable[[], Awaitable[Message]]


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
