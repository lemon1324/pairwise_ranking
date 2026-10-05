"""The request filters that sit in front of every route.

Each is a plain ASGI middleware rather than Starlette's ``BaseHTTPMiddleware``:
they look at headers, wrap ``receive`` or ``send``, and either step aside or
answer on the spot, and none of that needs a ``Request`` object or the task
juggling ``BaseHTTPMiddleware`` brings with it. Their refusals are short plain
text, like Starlette's own: they are answered before the application has
looked at the request, so there is no page to draw them into.

:func:`~src.web.app.create_app` decides the order they run in; see the comment
there.
"""

from typing import Iterable

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import ANY_HOST, LOOPBACK_HOSTS


# The methods that change something. A cross-site page can make a browser send
# any of them, but only these are worth refusing: a GET from elsewhere is a
# link, and every screen has to keep working when it is followed.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# The Sec-Fetch-Site values a change may come from: this application's own
# pages, and a request the user started themselves (typed, bookmarked).
SAME_ORIGIN_FETCH_SITES = frozenset({"same-origin", "none"})


def _host_name(host_header: str) -> str:
    """
    Take the host name out of a ``Host`` header.

    Args:
        host_header: The header as sent, with or without a port.

    Returns:
        str: The name in lower case, without the port, and without the
        brackets round an IPv6 address - the form the allowed-hosts entries
        are kept in. Starlette's own TrustedHostMiddleware splits on the first
        colon, which cuts an IPv6 address down to ``[``.
    """
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:].partition("]")[0]
    return host.partition(":")[0].rstrip(".")


class AllowedHostsMiddleware:
    """
    Refuse a request whose ``Host`` header names a host this server is not.

    The defence against DNS rebinding: a page that points its own name at this
    server's address gets past the browser's same-origin rule, but its requests
    still carry its own name, which is not on the list.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str]) -> None:
        """
        Args:
            app: The application to guard.
            allowed_hosts: The configured names, already checked and lower
                case. :data:`~src.web.config.LOOPBACK_HOSTS` are added to them.
        """
        self.app = app
        patterns = tuple(allowed_hosts)
        self.allow_any = ANY_HOST in patterns
        self.exact = frozenset(LOOPBACK_HOSTS) | {
            p for p in patterns if not p.startswith("*.")
        }
        # Kept with the leading dot, so *.example.lan matches a.example.lan and
        # not example.lan or badexample.lan.
        self.suffixes = tuple(p[1:] for p in patterns if p.startswith("*."))

    def allows(self, host_header: str) -> bool:
        """
        Whether a ``Host`` header names an allowed host.

        Args:
            host_header: The header as sent.

        Returns:
            bool: True if the request may go on.
        """
        if self.allow_any:
            return True
        host = _host_name(host_header)
        return host in self.exact or host.endswith(self.suffixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or self.allows(
            Headers(scope=scope).get("host", "")
        ):
            await self.app(scope, receive, send)
            return
        response = PlainTextResponse("Invalid host header", status_code=400)
        await response(scope, receive, send)


def is_cross_site(headers: Headers) -> bool:
    """
    Whether a browser says a request came from a page on another site.

    ``Sec-Fetch-Site`` decides when it is there, which it is in every current
    browser. Without it, ``Origin`` is compared with ``Host``: a reverse proxy
    that forwards the ``Host`` it was sent (Nginx Proxy Manager does) keeps the
    two equal for this application's own pages, under any root path. A request
    with neither is not from a browser that could be tricked into sending it,
    so it passes.

    Args:
        headers: The request headers.

    Returns:
        bool: True if the request should be refused.
    """
    fetch_site = headers.get("sec-fetch-site")
    if fetch_site is not None:
        return fetch_site.strip().lower() not in SAME_ORIGIN_FETCH_SITES

    origin = headers.get("origin")
    if origin is None:
        return False
    origin = origin.strip().lower()
    # "null" is what a sandboxed frame or a file:// page sends: nowhere this
    # application's own forms live.
    if origin == "null":
        return True
    authority = origin.partition("://")[2].partition("/")[0]
    return authority != headers.get("host", "").strip().lower()


class SameOriginMiddleware:
    """
    Refuse a change a page on another site asked the browser to make.

    There is no login to protect, so a CSRF token would guard nothing a
    header check does not: what matters is that a page elsewhere on the LAN,
    or on the internet, cannot delete a project by posting a hidden form.
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Args:
            app: The application to guard.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in UNSAFE_METHODS
            and is_cross_site(Headers(scope=scope))
        ):
            response = PlainTextResponse(
                "Cross-site request refused", status_code=403
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
