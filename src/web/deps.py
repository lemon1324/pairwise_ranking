"""What every route asks the application for.

Three dependencies, and the first of them is the reason this module exists.

:func:`get_current_user` returns a fixed local principal and will go on doing
so for as long as the application is a single-user thing on a LAN. Every route
depends on it anyway, from the first one onwards, because the day it starts
reading ``Remote-User`` from a forward-auth proxy or running an OIDC code flow
is the day it must already be threaded through every screen. Adding the seam
later means editing every route; adding it now costs one argument each.
"""

import logging
from dataclasses import dataclass, field

from fastapi import Depends, Request

from src.app.session import ProjectSession

from .config import WebConfig
from .registry import ProjectRegistry


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    """
    Who is making a request.

    Shaped after what a forward-auth proxy hands over - a name, something to
    show, and the groups the user is in - so that filling it from
    ``Remote-User`` and ``Remote-Groups`` later changes this module and nothing
    else.

    Attributes:
        name: The stable identifier, which is what any future per-user data
            would be keyed by.
        display_name: The name to put on screen.
        groups: The groups the user belongs to, empty while there is no
            directory to ask.
    """

    name: str
    display_name: str
    groups: tuple[str, ...] = field(default=())


# The one user of an unauthenticated installation. Not built per request: there
# is exactly one of them, and comparing identity is a fair way to assert that
# nothing has started inventing principals of its own.
LOCAL_PRINCIPAL = Principal(name="local", display_name="Local user")


def get_config(request: Request) -> WebConfig:
    """
    Return the configuration the application was built with.

    Args:
        request: The incoming request.

    Returns:
        WebConfig: The application's configuration.
    """
    return request.app.state.config


def get_current_user(request: Request) -> Principal:
    """
    Identify the user making a request.

    Args:
        request: The incoming request.

    Returns:
        Principal: :data:`LOCAL_PRINCIPAL`, because
        :data:`~src.web.config.AUTH_MODE_NONE` is the only mode implemented.
        The other modes read the request instead, which is why this takes one.
    """
    return LOCAL_PRINCIPAL


def get_registry(request: Request) -> ProjectRegistry:
    """
    Return the application's open-project cache.

    Args:
        request: The incoming request.

    Returns:
        ProjectRegistry: The one registry over the configured data directory.
    """
    return request.app.state.registry


def get_session(
    project_id: str, registry: ProjectRegistry = Depends(get_registry)
) -> ProjectSession:
    """
    Open the project a route was asked about, for reading.

    Reads through :meth:`~src.web.registry.ProjectRegistry.session`, which
    checks whether the file moved on disk and reloads it if so, as every
    screen's GET must. Routes that **change** a project take the registry
    instead and go through :meth:`~src.web.registry.ProjectRegistry.mutate`,
    which holds the file's lock for the whole edit; this one lets go of it
    before the route runs, so it is for rendering only.

    Args:
        project_id: The project's file name, from the route's path.
        registry: The open-project cache.

    Returns:
        ProjectSession: The session over that project.

    Raises:
        ProjectNotFoundError: If the id names no project in the data directory.
        ProjectFormatError: If the file's format version is unusable.
        ProjectUnreadableError: If the file cannot be read or parsed.
    """
    return registry.session(project_id)
