"""Where the screens live, written down once.

Every address in this application is built here rather than by hand, for two
reasons.

**A project is addressed by file name, and a file name is not a URL.** Names
come from the filesystem, not from this application: the desktop app lets a
user save ``Cost #1.pairrank``, and a link written straight into an ``href``
would lose everything from the ``#`` onwards. So a name is percent-encoded as
one path segment, always, by :func:`project_url`.

**Four screens do not exist yet.** The register links to Items, Compare,
Rankings and Settings, and the sheet tabs on those screens link to each other,
but only the register is built. ``url_for`` cannot name a route that has not
been registered, so the paths are composed from :data:`PROJECTS_PREFIX`
instead - which makes this module the contract the later chunks have to meet:
a screen named in :data:`SHEET_TABS` is served at
``{root_path}/projects/{file name}/{slug}``.

The reverse proxy's prefix is read from the request's ``root_path`` and never
from the URL, so every path built here carries the prefix and none of them
carries a scheme or a host.
"""

from urllib.parse import quote, urlencode

from starlette.requests import Request


# Everything about one project hangs off this, the register off the root.
PROJECTS_PREFIX = "/projects"

# The four sheets of an open project, as (slug, label), in tab order. The slug
# is the last segment of the screen's URL and the label is what the tab says.
SHEET_TABS = (
    ("items", "Items"),
    ("compare", "Compare"),
    ("rankings", "Rankings"),
    ("settings", "Settings"),
)

# The sheet a project opens on: Compare, as on the desktop. (It pointed at
# Items while phase 6 had built Items and nothing else.)
DEFAULT_SHEET = "compare"


def root_path(request: Request) -> str:
    """
    Read the prefix a reverse proxy serves this application under.

    Args:
        request: The incoming request.

    Returns:
        str: The prefix, empty when the application is served at the root.
    """
    return request.scope.get("root_path", "")


def register_url(request: Request, **query) -> str:
    """
    Build the address of the drawing register.

    Args:
        request: The incoming request.
        **query: Query parameters to carry, e.g. ``form="new"``. A parameter
            whose value is None or empty is left out, so a caller can pass the
            optional ones unconditionally.

    Returns:
        str: The register's path, with the proxy prefix and the query on it.
    """
    pairs = [(key, str(value)) for key, value in query.items() if value]
    suffix = f"?{urlencode(pairs)}" if pairs else ""
    return f"{root_path(request)}/{suffix}"


def project_url(request: Request, project_id: str, screen: str) -> str:
    """
    Build the address of one screen or action of one project.

    Args:
        request: The incoming request.
        project_id: The project's file name, as it is on disk.
        screen: The last segment: a slug from :data:`SHEET_TABS`, or one of the
            register's own verbs - ``open``, ``download``, ``callout``,
            ``duplicate``.

    Returns:
        str: The path, with the proxy prefix on it and the file name encoded as
        a single segment.
    """
    name = quote(project_id, safe="")
    return f"{root_path(request)}{PROJECTS_PREFIX}/{name}/{screen}"
