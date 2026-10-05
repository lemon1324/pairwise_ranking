"""Environment-driven configuration for the web process.

Everything the container operator can set lives here, read once into an
immutable :class:`WebConfig`. The application factory takes a config rather
than reading ``os.environ`` itself, so a test can build an app over a temporary
data directory without touching the process environment.

Names are prefixed ``PAIRRANK_`` because the Unraid template drops them into a
shared container environment alongside ``PUID``, ``PGID`` and ``TZ``.
"""

import ipaddress
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)

# Environment variable names, together in one place because the Unraid template
# and the Dockerfile both have to spell them the same way.
DATA_DIR_VAR = "PAIRRANK_DATA_DIR"
PORT_VAR = "PAIRRANK_PORT"
ROOT_PATH_VAR = "PAIRRANK_ROOT_PATH"
SECRET_KEY_VAR = "PAIRRANK_SECRET_KEY"
AUTH_MODE_VAR = "PAIRRANK_AUTH_MODE"
LOG_LEVEL_VAR = "PAIRRANK_LOG_LEVEL"
HOST_VAR = "PAIRRANK_HOST"
ALLOWED_HOSTS_VAR = "PAIRRANK_ALLOWED_HOSTS"

# The bind mount the Unraid template points at the appdata share.
DEFAULT_DATA_DIR = "/data"

DEFAULT_PORT = 8080

# Loopback only, so a developer's ``python web_main.py`` is not an
# unauthenticated server on whatever network the laptop is on. The image sets
# 0.0.0.0, because inside a container loopback is unreachable from the
# published port.
DEFAULT_HOST = "127.0.0.1"

# Host names every request may arrive under, whatever the operator lists: the
# image's HEALTHCHECK, the CI smoke test and a developer's browser all reach
# the server this way, and none of them is something a DNS-rebinding page can
# make a browser call.
LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")

# The allowed-hosts entry that switches the check off.
ANY_HOST = "*"

# The only authentication mode that exists yet. The plan's later modes are
# named here so that the error raised by a typo says what the alternatives will
# be, and so that grepping for them finds this list.
AUTH_MODE_NONE = "none"
PLANNED_AUTH_MODES = ("proxy", "oidc")

DEFAULT_LOG_LEVEL = "INFO"

# The level names uvicorn will accept. It looks the name up in a plain dict, so
# a name this module tolerated but uvicorn has never heard of is not a chatty
# log - it is a KeyError out of the server's own startup, which is the one
# failure the readable "Cannot start" message in :mod:`web_main` cannot report.
# TRACE is uvicorn's own and is finer than DEBUG; the standard library has no
# such level and simply logs more than asked.
UVICORN_LOG_LEVELS = frozenset(
    {"critical", "error", "warning", "info", "debug", "trace"}
)

# Names an operator plausibly writes that the standard library answers to and
# uvicorn does not. Mapped rather than refused, because a container that
# printed nothing over a synonym would be worse than one that logs.
LOG_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}

# One line per record, with the logger name, because a server's log is read
# after the fact by someone who was not watching: they need to know which part
# of the process spoke and when, which a bare message does not say.
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


@dataclass(frozen=True)
class WebConfig:
    """
    Everything the web process reads from its environment.

    Attributes:
        data_dir: The directory holding the ``.pairrank`` projects. Projects
            are addressed by file name within it and never by path.
        port: The port :mod:`web_main` binds.
        root_path: The subpath a reverse proxy serves the application under,
            empty when it is served at the root. Always either empty or a
            leading-slash path with no trailing slash.
        secret_key: The key signing the session cookie.
        secret_key_generated: Whether the key was generated for this process
            because none was configured. A generated key is fine for a LAN
            session but logs every user out on restart, so the fact is carried
            rather than only warned about once.
        auth_mode: How users are identified. Only :data:`AUTH_MODE_NONE` is
            implemented; :mod:`src.web.deps` is the seam the others plug into.
        log_level: The root log level name, always upper case and always one
            :data:`UVICORN_LOG_LEVELS` holds, so it can be handed to either
            logger without a second opinion about what it means.
        host: The address :mod:`web_main` binds.
        allowed_hosts: The host names, lower case, a request's ``Host`` header
            may carry besides :data:`LOOPBACK_HOSTS`, which are always allowed.
            An entry may be ``*.example.lan`` for any subdomain, or
            :data:`ANY_HOST` to allow every name. Empty, the default, allows
            loopback only - so a test or a caller that builds a config by hand
            gets the closed answer unless it asks for another.
    """

    data_dir: Path
    port: int
    root_path: str
    secret_key: str
    secret_key_generated: bool
    auth_mode: str
    log_level: str
    host: str = DEFAULT_HOST
    allowed_hosts: tuple = ()


def _normalized_root_path(raw: str) -> str:
    """
    Put a configured root path into the one shape the rest of the code expects.

    Args:
        raw: The value as configured, which an operator may well have written
            with or without either slash.

    Returns:
        str: The empty string, or a path beginning with a slash and not ending
        in one - which is the form Starlette's ``root_path`` and ``url_for``
        agree on.
    """
    path = raw.strip().strip("/")
    return f"/{path}" if path else ""


def _port(raw: str) -> int:
    """
    Read a port number.

    Args:
        raw: The configured value.

    Returns:
        int: The port.

    Raises:
        ValueError: If the value is not a whole number in the port range. A
            container that cannot bind where its operator asked should say so
            and stop rather than quietly listen somewhere else.
    """
    try:
        port = int(raw)
    except ValueError as e:
        raise ValueError(f"{PORT_VAR} must be a whole number, got {raw!r}") from e

    if not 1 <= port <= 65535:
        raise ValueError(f"{PORT_VAR} must be between 1 and 65535, got {port}")
    return port


def _bind_host(raw: str) -> str:
    """
    Read the address to bind.

    Args:
        raw: The configured value.

    Returns:
        str: The address, or :data:`DEFAULT_HOST` when none was given.

    Raises:
        ValueError: If the value is plainly not an address - a URL, or a name
            with a space in it - which uvicorn would otherwise turn into a
            traceback rather than a readable refusal.
    """
    host = raw.strip()
    if not host:
        return DEFAULT_HOST
    if "/" in host or any(ch.isspace() for ch in host):
        raise ValueError(
            f"{HOST_VAR} must be an address to listen on, such as "
            f"{DEFAULT_HOST} or 0.0.0.0, got {raw!r}"
        )
    return host


def _host_pattern(entry: str) -> str:
    """
    Check one allowed-hosts entry and put it into the form requests are matched in.

    Args:
        entry: One comma-separated entry, already stripped.

    Returns:
        str: The entry in lower case, an IPv6 address without its brackets.

    Raises:
        ValueError: If the entry could never match a ``Host`` header: a URL, a
            name with a port, or a wildcard anywhere but a leading ``*.``. A
            list that silently matches nothing is how a server ends up
            refusing its own operator with no clue why.
    """
    pattern = entry.lower()
    if pattern.startswith("[") and pattern.endswith("]"):
        pattern = pattern[1:-1]
    if pattern == ANY_HOST:
        return pattern

    problem = ""
    if "/" in pattern or any(ch.isspace() for ch in pattern):
        problem = "is not a host name"
    elif "*" in pattern and (not pattern.startswith("*.") or "*" in pattern[1:]):
        problem = "can only use * as a whole leading label, as in *.example.lan"
    elif ":" in pattern:
        try:
            ipaddress.IPv6Address(pattern)
        except ValueError:
            problem = "has a port or scheme; list the bare host name"
    if problem:
        raise ValueError(f"{ALLOWED_HOSTS_VAR} entry {entry!r} {problem}")
    return pattern


def _allowed_hosts(raw: str) -> tuple:
    """
    Read the host names requests may arrive under.

    Args:
        raw: The configured comma-separated list.

    Returns:
        tuple: The entries, checked and lower-cased, in the order given.
        Empty when nothing was configured, which leaves loopback only.

    Raises:
        ValueError: If an entry could never match a request.
    """
    hosts = tuple(
        _host_pattern(entry.strip()) for entry in raw.split(",") if entry.strip()
    )
    if ANY_HOST in hosts:
        logger.warning(
            "%s includes %r, so requests are accepted under any host name. "
            "That re-opens the server to DNS rebinding; list the names it is "
            "reached by instead.",
            ALLOWED_HOSTS_VAR,
            ANY_HOST,
        )
    return hosts


def _auth_mode(raw: str) -> str:
    """
    Read the authentication mode.

    Args:
        raw: The configured value.

    Returns:
        str: The mode.

    Raises:
        ValueError: If the mode is anything but "none". Falling back to "none"
            on an unrecognized value is the one wrong answer here: it would
            turn a misspelt ``proxy`` into an unauthenticated application that
            looks configured.
    """
    mode = raw.strip().lower() or AUTH_MODE_NONE
    if mode != AUTH_MODE_NONE:
        planned = ", ".join(PLANNED_AUTH_MODES)
        raise ValueError(
            f"{AUTH_MODE_VAR}={raw!r} is not supported yet; the only mode "
            f"implemented is {AUTH_MODE_NONE!r} ({planned} are planned)"
        )
    return mode


def _log_level(raw: str) -> str:
    """
    Read the log level, settling on a name both loggers answer to.

    An unrecognized level is forgiven rather than refused - losing the log is a
    worse way to learn about a typo than a slightly chatty log - but the
    forgiving has to happen *here*, once. Handing the raw name on to uvicorn as
    well would leave the two disagreeing, and uvicorn's disagreement is a
    KeyError during startup rather than a verbose log.

    Args:
        raw: The configured value.

    Returns:
        str: An upper-case level name from :data:`UVICORN_LOG_LEVELS`.
    """
    level = raw.strip().upper()
    level = LOG_LEVEL_ALIASES.get(level, level)
    if level.lower() not in UVICORN_LOG_LEVELS:
        known = ", ".join(sorted(name.upper() for name in UVICORN_LOG_LEVELS))
        logger.warning(
            "%s=%r is not a log level; using %s. The levels are: %s.",
            LOG_LEVEL_VAR,
            raw,
            DEFAULT_LOG_LEVEL,
            known,
        )
        return DEFAULT_LOG_LEVEL
    return level


def load_config(env: dict = None) -> WebConfig:
    """
    Read the configuration out of the environment.

    Args:
        env: The mapping to read, defaulting to the process environment.

    Returns:
        WebConfig: The configuration, with defaults filled in and a session key
        generated if none was given.

    Raises:
        ValueError: If a value is present but unusable.
    """
    source = os.environ if env is None else env

    secret_key = (source.get(SECRET_KEY_VAR) or "").strip()
    generated = not secret_key
    if generated:
        secret_key = secrets.token_urlsafe(32)
        logger.warning(
            "%s is not set; generating a random session key for this process. "
            "Sessions will not survive a restart - set %s to keep them.",
            SECRET_KEY_VAR,
            SECRET_KEY_VAR,
        )

    return WebConfig(
        data_dir=Path(source.get(DATA_DIR_VAR) or DEFAULT_DATA_DIR),
        port=_port(source.get(PORT_VAR) or str(DEFAULT_PORT)),
        root_path=_normalized_root_path(source.get(ROOT_PATH_VAR) or ""),
        secret_key=secret_key,
        secret_key_generated=generated,
        auth_mode=_auth_mode(source.get(AUTH_MODE_VAR) or ""),
        log_level=_log_level(source.get(LOG_LEVEL_VAR) or DEFAULT_LOG_LEVEL),
        host=_bind_host(source.get(HOST_VAR) or ""),
        allowed_hosts=_allowed_hosts(source.get(ALLOWED_HOSTS_VAR) or ""),
    )


def configure_logging(level: str = DEFAULT_LOG_LEVEL) -> None:
    """
    Point the root logger at stderr in the process-wide format.

    Called by :mod:`web_main` before the application is built, and by nothing
    else: a library that configures logging on import steals the decision from
    whoever imported it, and the desktop app is one of the things that imports
    this package's neighbours.

    Args:
        level: The root log level name. An unrecognized name falls back to
            INFO rather than raising, because losing the log is a worse way to
            learn about a typo in a log level than a slightly chatty log.
    """
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        force=True,
    )
