"""The application factory and the pages it falls back to.

:func:`create_app` builds one FastAPI application over one data directory.
Nothing here is a module-level singleton: a test builds an app over a temporary
directory by passing a :class:`~src.web.config.WebConfig`, and the process
entry point builds one from the environment. An ``app`` created at import time
would read the environment before anybody had a chance to say otherwise.

**The error handlers are the reason this file is longer than a factory.** A
project file can be unusable in ways that mean different things to the person
looking at the screen, and the whole point of :mod:`src.data.errors` is to keep
those apart: a file written by a newer version of the application is not
broken and will open again after an update, while a damaged file needs its
backup. Two failures, two pages, and no message-text matching in between.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from src.data.errors import NewerFormatError, ProjectFormatError

from .config import WebConfig, load_config
from .registry import ProjectNotFoundError, ProjectRegistry, ProjectUnreadableError
from .routes import placeholder


logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"

# Where the stylesheets, fonts and scripts are served from. Held as a constant
# because templates reach it through url_for("static", ...) and the capture
# harness needs to know it too.
STATIC_MOUNT = "/static"

# Status codes for the two format failures. Neither is really the browser's
# fault, but both are answers *about a named project* rather than signs that
# the server is unwell, and a 5xx would file them under "the application is
# broken" for anything watching. 409 says the project is in a state this
# application cannot work with; 422 says the file itself will not parse.
NEWER_FORMAT_STATUS = 409
DAMAGED_STATUS = 422


def _render_error(
    request: Request, template: str, status_code: int, **context
) -> Response:
    """
    Draw one of the error pages.

    Args:
        request: The request that failed.
        template: The template name under ``templates/errors/``.
        status_code: The status to answer with.
        **context: Extra values for the template.

    Returns:
        Response: The rendered page.
    """
    templates: Jinja2Templates = request.app.state.templates
    # Every error page offers a way back to the register, and it has to carry
    # the reverse proxy's prefix. url_for would do that, but the picker route
    # does not exist until phase 5 and an error page that errors is no use.
    #
    # The status goes into the context here rather than at each call site: a
    # caller passing it as a keyword as well as positionally is a TypeError
    # raised from inside an exception handler, which is the worst place in the
    # application to raise anything.
    context = {
        "home_url": f"{request.scope.get('root_path', '')}/",
        "status_code": status_code,
        **context,
    }
    return templates.TemplateResponse(
        request, f"errors/{template}", context, status_code=status_code
    )


def _install_error_handlers(app: FastAPI) -> None:
    """
    Map every failure a route can raise onto a page.

    Args:
        app: The application to install them on.
    """

    async def not_found(request: Request, exc: Exception) -> Response:
        """Answer for a project, or a URL, that is not there."""
        return _render_error(request, "not_found.html", 404)

    async def newer_format(request: Request, exc: NewerFormatError) -> Response:
        """Answer for a file written by a newer version of the application."""
        return _render_error(
            request,
            "newer_format.html",
            NEWER_FORMAT_STATUS,
            file_version=exc.file_version,
            supported_version=exc.supported_version,
        )

    async def damaged(request: Request, exc: Exception) -> Response:
        """Answer for a file that cannot be read as a project at all."""
        logger.warning("Refusing to open a damaged project: %s", exc)
        return _render_error(
            request, "damaged.html", DAMAGED_STATUS, reason=str(exc)
        )

    async def http_error(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        """
        Answer for the statuses raised as HTTPException.

        404 gets its own page; everything else shares the generic one, which
        carries the status so the page does not have to lie about which it is.
        """
        if exc.status_code == 404:
            return await not_found(request, exc)
        return _render_error(
            request, "http_error.html", exc.status_code, detail=exc.detail
        )

    async def unhandled(request: Request, exc: Exception) -> Response:
        """
        Answer for a bug.

        The traceback goes to the log and nothing but the fact goes to the
        page: this application is on a LAN behind a proxy, and a stack trace on
        screen is a habit worth not acquiring.
        """
        logger.exception("Unhandled error serving %s", request.url.path)
        return _render_error(request, "server_error.html", 500)

    app.add_exception_handler(ProjectNotFoundError, not_found)
    app.add_exception_handler(NewerFormatError, newer_format)
    # The base class catches what is left of the hierarchy, which in practice
    # is UnsupportedUpgradeError: a gap in the upgrade chain reads as damage
    # from the user's side of the screen. The order these are registered in
    # does not matter - Starlette walks the raised exception's MRO and takes
    # the first handler it finds, so NewerFormatError reaches its own handler
    # before ever reaching this one, wherever the two lines sit.
    app.add_exception_handler(ProjectFormatError, damaged)
    app.add_exception_handler(ProjectUnreadableError, damaged)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(Exception, unhandled)


def create_app(config: Optional[WebConfig] = None) -> FastAPI:
    """
    Build the web application.

    Args:
        config: The configuration to run with. Read from the environment when
            not given.

    Returns:
        FastAPI: The application, with its registry, templates and static files
        wired up.
    """
    config = config if config is not None else load_config()

    app = FastAPI(
        title="Pairwise Ranking",
        # Starlette strips this prefix off incoming paths and puts it back on
        # every url_for, which is what lets a reverse proxy serve the whole
        # application under a subpath without a single template knowing.
        root_path=config.root_path,
        # The screens are pages, not an API. A published schema would only
        # describe fragments nobody consumes programmatically.
        openapi_url=None,
    )

    app.state.config = config
    app.state.registry = ProjectRegistry(config.data_dir)
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Server-side session state behind a signed cookie: the frontend keeps
    # nothing it cannot afford to lose, but the signing is what makes the
    # cookie safe to trust once there is an authenticated user in it.
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.secret_key,
        same_site="lax",
        # Not https_only: the LAN deployment is plain HTTP behind the user's
        # own reverse proxy, and a secure-only cookie would simply never arrive.
        https_only=False,
    )

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(
        STATIC_MOUNT, StaticFiles(directory=str(STATIC_DIR)), name="static"
    )

    _install_error_handlers(app)

    # After the handlers, so a route that raises on its first request is
    # already answered by a page rather than by a bare traceback.
    app.include_router(placeholder.router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        """
        Report that the process is up.

        Deliberately dependency-free: the container's HEALTHCHECK calls it
        several times a minute and must not be answered by anything that reads
        a file, takes a lock or needs a user.

        Returns:
            JSONResponse: 200 and a small body.
        """
        return JSONResponse({"status": "ok"})

    logger.info(
        "Serving projects from %s (root path %r, auth mode %s)",
        config.data_dir,
        config.root_path,
        config.auth_mode,
    )
    return app
