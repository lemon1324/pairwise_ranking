# syntax=docker/dockerfile:1

# --- build: resolve the web dependencies into an in-project venv ------------
# Poetry is pinned to the version poetry.lock was written with; an unpinned
# install would pick up whatever is newest and could refuse or rewrite the lock.
FROM python:3.12-slim AS build

# NO_PIP: the venv is created without pip, so the runtime image carries no
# package installer the app never uses. Poetry installs into it with its own
# installer, not the venv's pip.
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_OPTIONS_NO_PIP=true \
    POETRY_NO_INTERACTION=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir poetry==2.5.1

WORKDIR /app
COPY pyproject.toml poetry.lock ./
# main and web only: the desktop group is PyQt6, which the web image must
# never carry, and dev is the test tooling.
RUN poetry sync --only main,web --no-root


# --- runtime: the venv and the application source, nothing else -------------
FROM python:3.12-slim

# tzdata: vote timestamps and project modified times are naive local times
# shared with the desktop app, so TZ has to mean something in here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PAIRRANK_DATA_DIR=/data \
    PAIRRANK_PORT=8080 \
    PAIRRANK_HOST=0.0.0.0

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY src ./src
COPY web_main.py ./
COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

# No VOLUME: projects should never quietly land in an anonymous volume nobody
# will find. An unmounted run with PUID/PGID set fails the entrypoint's write
# probe (the unprivileged user can't create /data). With neither set the
# entrypoint stays root, creates /data in the container's own layer, and the
# projects saved there are lost when the container is recreated.

EXPOSE 8080

# Straight at uvicorn, so no proxy in between: /healthz answers at the bare
# path whether or not PAIRRANK_ROOT_PATH is set (Starlette only strips the
# prefix when a request carries it). The venv's python does the request, so
# the image needs no curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + (os.environ.get('PAIRRANK_PORT') or '8080').strip() + '/healthz', timeout=4)"]

ENTRYPOINT ["/entrypoint.sh"]
# Never add uvicorn workers (or run several replicas on one data folder): the
# registry's per-path locks in src/web/registry.py are in-process, so a second
# process would write the same project files without them. web_main.py runs a
# single process on purpose.
CMD ["python", "web_main.py"]
