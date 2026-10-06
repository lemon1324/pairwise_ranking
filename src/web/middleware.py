"""The request filters that sit in front of every route.

Each is a plain ASGI middleware rather than Starlette's ``BaseHTTPMiddleware``:
they look at headers, wrap ``receive`` or ``send``, and either step aside or
answer on the spot, and none of that needs a ``Request`` object or the task
juggling ``BaseHTTPMiddleware`` brings with it. Their refusals are short plain
text, like Starlette's own: they are answered before the application has
looked at the request, so there is no page to draw them into. The one
exception is a body found too large while a route is reading it, which the
application's own error page answers.

:func:`~src.web.app.create_app` decides the order they run in; see the comment
there.
"""

from typing import Iterable

from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


def _split_port(authority: str) -> tuple:
    """
    Split a ``host[:port]`` authority into its name and port.

    Args:
        authority: A ``Host`` header or the authority of an ``Origin``,
            already lower case.

    Returns:
        tuple: The name, an IPv6 address keeping its brackets, and the port,
        or an empty string when there is none.
    """
    if authority.startswith("["):
        name, _, rest = authority.partition("]")
        return name + "]", rest.partition(":")[2]
    name, _, port = authority.partition(":")
    return name, port


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
    browser except over plain HTTP to a name other than localhost. Without it,
    ``Origin`` is compared with ``Host``: a reverse proxy that forwards the
    host name it was sent, with or without the port (Nginx Proxy Manager drops
    it), keeps the two matching for this application's own pages, under any
    root path. A request with neither is not from a browser that could be tricked into sending it,
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
    host = headers.get("host", "").strip().lower()
    host_name, host_port = _split_port(host)
    if not host_port:
        # Nginx Proxy Manager forwards the host name without the port, so a
        # Host with no port matches an Origin on any port of that name. Another
        # port on the same name then counts as this site: fine on a LAN.
        return _split_port(authority)[0] != host_name
    return authority != host


class RequestTooLarge(HTTPException):
    """
    Raised out of ``receive`` when a body without a declared length runs past the limit.

    FastAPI's HTTPException rather than a private class, because FastAPI turns
    anything else raised while it parses a form into a 400 "error parsing the
    body", and re-raises only this. The application's handlers then draw the
    413 as its usual error page.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=413, detail="That request is too large to be served."
        )


class BodySizeLimitMiddleware:
    """
    Refuse a request body larger than any form or import could need.

    Starlette spools a multipart upload to a temporary file before the import
    route gets to look at its size, so without this a single request can fill
    the container's disk, however small the route's own limit.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        """
        Args:
            app: The application to guard.
            max_bytes: The largest body allowed through.
        """
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # A declared length is refused before a byte is read. One that does
        # not parse is left to the server, which has already accepted it.
        declared = Headers(scope=scope).get("content-length", "")
        if declared.strip().isdigit() and int(declared) > self.max_bytes:
            await self._refuse(scope, receive, send)
            return

        # A chunked body has no length to check, so it is counted as it comes.
        received = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge()
            return message

        async def watching_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, watching_send)
        except RequestTooLarge:
            # Normally the application's handlers have answered already. If
            # the body was read somewhere they do not reach, answer here, or -
            # with a response half sent - let the server drop the connection.
            if response_started:
                raise
            await self._refuse(scope, receive, send)

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send) -> None:
        """Answer 413 without reading the body."""
        response = PlainTextResponse("Request body too large", status_code=413)
        await response(scope, receive, send)


class SecurityHeadersMiddleware:
    """
    Add the browser-hardening headers to every response.

    A header a route set on purpose is left alone: these are defaults, not
    overrides.
    """

    def __init__(self, app: ASGIApp, headers: dict) -> None:
        """
        Args:
            app: The application whose responses to mark.
            headers: Header names and values to add where missing.
        """
        self.app = app
        self.headers = dict(headers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def marking_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, marking_send)


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
