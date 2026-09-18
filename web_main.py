"""Entry point for the web application.

``python web_main.py`` is what the container runs and what a developer runs to
see the app. It configures logging, reads the environment once, and hands
uvicorn an application built from that configuration - rather than an import
string, so the configuration errors surface here, with a readable message,
instead of inside a worker's import.

The desktop app's entry point is ``main.py`` and is untouched by any of this.
"""

import logging
import sys

import uvicorn

from src.web.app import create_app
from src.web.config import configure_logging, load_config


logger = logging.getLogger(__name__)

# Bound on every interface because the process lives in a container whose only
# route in is a published port; binding loopback would make it unreachable.
HOST = "0.0.0.0"

# The application sits behind the user's own reverse proxy on a LAN, so the
# forwarded headers are as trustworthy as anything else on that network and
# there is no sensible fixed list of proxy addresses to name. Without this,
# every request looks like it came from the proxy over plain HTTP and the
# redirects the proxy hands back point at the wrong scheme.
FORWARDED_ALLOW_IPS = "*"


def main() -> int:
    """
    Run the web server until it is stopped.

    Returns:
        int: A process exit status - 0 when the server shut down cleanly, 2
        when the configuration could not be read.
    """
    configure_logging()

    try:
        config = load_config()
    except ValueError as e:
        logger.error("Cannot start: %s", e)
        return 2

    configure_logging(config.log_level)

    uvicorn.run(
        create_app(config),
        host=HOST,
        port=config.port,
        proxy_headers=True,
        forwarded_allow_ips=FORWARDED_ALLOW_IPS,
        # Not passed as uvicorn's root_path: the application already carries it,
        # and setting it in both places prefixes it twice.
        log_config=None,
        log_level=config.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
