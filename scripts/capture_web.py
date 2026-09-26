#!/usr/bin/env python
"""Capture the running web app at review widths, in both themes.

Phases 5-8 compare each screen against the mockup it was ported from. This is
the thing that makes the comparison possible: it boots the app on a scratch
data directory, drives headless Chrome over CDP, and drops one PNG per screen
per width per theme into ``.impeccable/review/``.

Usage (from WSL, with the Windows venv - see "Why the Windows venv" below)::

    ./.venv/Scripts/python.exe scripts/seed_capture_data.py \\
        .scratch/capture-data
    ./.venv/Scripts/python.exe scripts/capture_web.py \\
        --data-dir .scratch/capture-data \\
        register=/ items=/projects/demo/items

The data directory has to live somewhere Windows can see - under ``/mnt/...``,
not in WSL's own filesystem, which the server process cannot reach at all - and,
by the owner's rule, inside the repository: ``.scratch/`` at its root is
excluded from git for exactly this. The Chrome profile this script makes for
itself goes there too (``scratch_dir``), and is removed afterwards.

Each positional argument is an app path, optionally prefixed with ``label=`` to
name the files. Without a label the path is slugified: ``/healthz`` becomes
``healthz``, ``/projects/demo/items`` becomes ``projects-demo-items``. The
register is served at ``/``, which slugifies to nothing, so it needs a label of
its own. Files land as
``.impeccable/review/web-<label>-<width>-<theme>.png`` - for example
``web-register-390-dark.png``. That directory is in ``.git/info/exclude``, so the
captures never reach a commit.

Options worth knowing:

``--data-dir PATH``   (required) the ``PAIRRANK_DATA_DIR`` the app is booted
                      against. A WSL path (``/mnt/c/...``) is translated to its
                      Windows form, because the server is a Windows process.
``--size WxH``        repeatable; default 390x844, 1280x900, 1920x1080.
``--theme NAME``      repeatable; default light and dark. The theme is forced
                      with ``?theme=`` on the URL, which ``base.html`` reads
                      before first paint - no browser emulation involved.
``--out-dir PATH``    default ``.impeccable/review``.
``--port N``          default 8099.
``--base-url URL``    capture an already-running server instead of booting one.

Every capture reads ``window.innerWidth`` back out of the page and compares it
to the width that was asked for. A mismatch aborts the whole run::

    capture_web.py: viewport width mismatch at /: asked for 390 CSS px,
    the page laid out at 500

which is the failure this script exists to prevent. Windows Chrome refuses to
make a headless window narrower than 500 CSS px - ``--window-size=390,844``
silently yields ``innerWidth == 500`` under both ``--headless=new`` and
``--headless=old``, and ``--force-device-scale-factor`` does not change it. So
the width is set with CDP ``Emulation.setDeviceMetricsOverride`` instead, which
sets the layout viewport directly and is not clamped. The read-back is there so
that if a future Chrome clamps that too, the run stops instead of quietly
filing a 500 px screenshot as a phone.

Two more things it refuses to file, both found in phase 5c.

**A sheet with no callout.** Every screen in this set fetches the selected
row's callout *after* the load event: sheet.js selects on ``DOMContentLoaded``,
htmx hears ``sheet:select`` and does an XHR. So ``readyState === "complete"``
is reached with the fragment still in the air - 8-22 ms early on loopback, and
nothing about that margin is promised. The shutter therefore waits until the
page has no request in flight, and then refuses outright if a selected row asks
for a callout and ``#row-callout`` is still empty. A capture missing its
callout looks exactly like an ordinary sheet, which is why this is a hard
failure and not a warning. Compare draws no rows, so it has a probe of its
own (``COMPARE_CHECK``, chunk 7b): both views present and, unless the sheet is
in its empty state, both view bodies. Settings draws neither, so it has one
too (``SETTINGS_CHECK``, chunk 8b): parameter rows with their controls, a
Status cell that says something, and settings.js done.

**A page with no focus.** A headless window is not the focused window, so
``document.hasFocus()`` is false, nothing matches ``:focus`` or
``:focus-visible``, and no capture can show a focus ring - including on the
field a form callout has just put the caret in. CDP's
``Emulation.setFocusEmulationEnabled`` makes the renderer treat the page as
focused, which is the state the person looking at the screen is in.

``.impeccable/review/web-frame.html`` does the same job by hand for a human
with a real browser open: it iframes an arbitrary app URL at a fixed size.

**Why the Windows venv.** The venv is Windows-only, so ``web_main.py`` runs as
a Windows process and Chrome is a Windows process; both agree that the server
is at ``127.0.0.1``. Running this script under WSL's python instead would put
the server behind the WSL NAT, where Chrome cannot reach it, and would put
Chrome's debugging port somewhere WSL cannot reach either. It also means the
environment does not have to cross the WSL/Windows boundary, which otherwise
needs ``WSLENV``.

Nothing here is imported by the application, and it deliberately uses only the
standard library: the CDP client below is ~60 lines of websocket framing rather
than a dependency the container image would have to carry.
"""

import argparse
import base64
import json
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


PROGRAM = "capture_web.py"

REPO_ROOT = Path(__file__).resolve().parent.parent

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

DEFAULT_PORT = 8099
DEFAULT_OUT_DIR = REPO_ROOT / ".impeccable" / "review"

# Everything these scripts make for themselves - a Chrome profile, a seeded data
# directory - goes here, inside the repository and excluded from git by
# ``.git/info/exclude``. Nothing is written outside the repository (the owner's
# rule), which rules out ``tempfile``'s default of Windows ``%TEMP%``.
SCRATCH_ROOT = REPO_ROOT / ".scratch"

# The three review widths: a phone, the narrow desktop where the drawing frame
# still shows 6 zones, and the wide one where it shows 8. Heights are the usual
# companions of each - nothing depends on them but the amount of sheet visible.
DEFAULT_SIZES = ((390, 844), (1280, 900), (1920, 1080))

DEFAULT_THEMES = ("light", "dark")

# Generous, because the first boot on a cold venv imports fastapi, and because
# a failure here is nearly always "the port is taken" rather than "slow".
SERVER_BOOT_TIMEOUT_S = 40.0
SERVER_POLL_INTERVAL_S = 0.1

CHROME_BOOT_TIMEOUT_S = 30.0

# How long one page may take to reach readyState complete with its fonts
# loaded. The app is on loopback with no network fetches, so this is only ever
# hit by something being wrong.
PAGE_READY_TIMEOUT_S = 20.0
PAGE_POLL_INTERVAL_S = 0.05

# After the page says it is ready, one more frame for the layout to settle
# before the shutter. Small enough not to matter, big enough that a font swap
# is never caught halfway.
SETTLE_S = 0.25

# How long a page may keep a request in flight after it has otherwise gone
# quiet. See QUIET_PROBE: the screens fetch their callouts *after* the load
# event, so "ready" is not the same thing as "finished".
QUIET_TIMEOUT_S = 10.0

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Installed before any of the page's own scripts run, so it sees the first
# request the page makes.
#
# Every screen in this set fetches the selected row's callout *after* the load
# event - sheet.js selects on DOMContentLoaded, htmx hears `sheet:select` and
# does an XHR - so `readyState === "complete"` is reached with the callout
# still in the air. Measured on loopback, it lands 8-22 ms after complete,
# which SETTLE_S covered by luck rather than by design: nothing here waited for
# it and nothing checked it had arrived, so a slower machine would have filed a
# sheet with no callout on it and no one would have known. This counts requests
# instead, and the shutter waits for the count to reach zero.
QUIET_PROBE = """
(() => {
  window.__capturePending = 0;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    window.__capturePending += 1;
    this.addEventListener(
      "loadend",
      () => { window.__capturePending -= 1; },
      { once: true }
    );
    return send.apply(this, args);
  };
  const fetch0 = window.fetch;
  if (fetch0) {
    window.fetch = function (...args) {
      window.__capturePending += 1;
      return fetch0.apply(this, args).finally(() => {
        window.__capturePending -= 1;
      });
    };
  }
})();
"""

# The one thing a screenshot of this design set can be silently wrong about.
# A row the engine has selected carries `hx-get` (the parts_row contract), and
# its callout belongs in `#row-callout`; an empty host next to a selected row
# means the fragment never arrived, which looks like a perfectly ordinary
# sheet. Checked after the wait, so the failure is loud.
CALLOUT_CHECK = """
(() => {
  const row = document.querySelector('.bom-row[aria-selected="true"][hx-get]');
  const host = document.getElementById("row-callout");
  if (!row || !host) return "";
  return host.children.length ? "" : (row.dataset.id || "(unnamed row)");
})()
"""


# The same, for Compare, which draws no rows and so passes the callout check
# whatever state it is in. A pair sheet is two views; unless the sheet is in
# its empty state (`.is-empty`, on .frame-inner in the app and on #frame in the
# mockup), each view has a body with the item in it. A page with no `.views`
# is not a pair sheet and is not this check's business.
COMPARE_CHECK = """
(() => {
  const views = document.querySelector(".views");
  if (!views) return "";
  const count = views.querySelectorAll(".view").length;
  if (count !== 2) return count + " views";
  if (document.querySelector(".frame-inner.is-empty, #frame.is-empty")) return "";
  const bodies = views.querySelectorAll(".view .view-body").length;
  return bodies === 2 ? "" : bodies + " view bodies";
})()
"""


# The same, for Settings (chunk 8b), a specification sheet with no rows and no
# pair. The mockup builds its parameter table in script; the app draws it on
# the server and settings.js then works out Save's state and the Status cell,
# and marks the form `data-ready` when it has. So a sheet whose table is empty,
# whose rows lack a control, whose Status says nothing, or whose script has not
# run yet is refused. A page with no `.spec-sheet` is not this check's business.
SETTINGS_CHECK = """
(() => {
  if (!document.querySelector(".spec-sheet")) return "";
  const rows = document.querySelectorAll('#params tr[id^="row-"]');
  if (!rows.length) return "no parameter rows";
  for (const row of rows) {
    if (!row.querySelector("input")) return "no control in " + row.id;
  }
  const status = document.getElementById("status");
  if (!status || !status.textContent.trim()) return "an empty Status cell";
  const form = document.querySelector("form#settings[data-number-pattern]");
  if (form && form.dataset.ready !== "1") return "settings.js not yet run";
  return "";
})()
"""


class CaptureError(Exception):
    """A capture could not be taken, or was taken wrongly and must not be kept."""


# --------------------------------------------------------------------------
# A very small CDP client
# --------------------------------------------------------------------------


class WebSocket:
    """
    The client half of RFC 6455, in as little code as CDP needs.

    CDP speaks text frames over a websocket and the standard library has no
    websocket client, so this is the alternative to a dependency. It handles
    what Chrome actually sends: text and continuation frames of any length,
    pings, and close. It is synchronous and single-threaded, which suits a
    script that asks one question at a time.

    Attributes:
        _sock: The connected socket.
        _reader: A buffered reader over it, so that a frame header and its
            payload can be read exactly rather than guessed at.
    """

    OP_CONTINUATION = 0x0
    OP_TEXT = 0x1
    OP_BINARY = 0x2
    OP_CLOSE = 0x8
    OP_PING = 0x9
    OP_PONG = 0xA

    def __init__(self, url: str, timeout: float = 30.0):
        """
        Open a websocket to a ``ws://`` URL and complete the handshake.

        Args:
            url: The endpoint, as CDP's ``/json`` listing gives it.
            timeout: Socket timeout in seconds for every read and write.

        Raises:
            CaptureError: If the server does not accept the upgrade.
        """
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "ws":
            raise CaptureError(f"only ws:// is supported, got {url!r}")

        self._sock = socket.create_connection(
            (parts.hostname, parts.port or 80), timeout=timeout
        )
        self._sock.settimeout(timeout)
        self._reader = self._sock.makefile("rb")

        resource = parts.path + (f"?{parts.query}" if parts.query else "")
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        # No Origin header on purpose: Chrome rejects debugger connections that
        # carry one it was not told to allow, and a client that sends none is
        # treated as a non-browser tool, which is exactly what this is.
        request = (
            f"GET {resource} HTTP/1.1\r\n"
            f"Host: {parts.hostname}:{parts.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._sock.sendall(request.encode("ascii"))

        status = self._reader.readline().decode("latin-1").strip()
        if "101" not in status:
            raise CaptureError(f"websocket upgrade refused: {status!r}")
        while True:
            line = self._reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break

    def send_text(self, text: str) -> None:
        """
        Send one masked text frame.

        Args:
            text: The payload. CDP messages are small enough that this never
                needs to fragment.
        """
        payload = text.encode("utf-8")
        header = bytearray([0x80 | self.OP_TEXT])
        mask = secrets.token_bytes(4)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def recv_text(self) -> str:
        """
        Read frames until a whole text message has arrived.

        Returns:
            str: The message. Screenshots come back as multi-megabyte base64,
            which Chrome fragments, so continuation frames are reassembled
            here rather than assumed away.

        Raises:
            CaptureError: If the connection closes first.
        """
        chunks = []
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode == self.OP_CLOSE:
                raise CaptureError("the browser closed the debugging connection")
            if opcode == self.OP_PING:
                self._send_control(self.OP_PONG, payload)
                continue
            if opcode == self.OP_PONG:
                continue
            chunks.append(payload)
            if fin:
                return b"".join(chunks).decode("utf-8")

    def _read_frame(self) -> tuple:
        """
        Read one frame.

        Returns:
            tuple: ``(fin, opcode, payload)``. Server frames are never masked,
            so no unmasking is needed.

        Raises:
            CaptureError: If the stream ends mid-frame.
        """
        head = self._read_exactly(2)
        fin = bool(head[0] & 0x80)
        opcode = head[0] & 0x0F
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exactly(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exactly(8))[0]
        return fin, opcode, self._read_exactly(length)

    def _read_exactly(self, count: int) -> bytes:
        """
        Read exactly ``count`` bytes.

        Args:
            count: How many bytes the frame says are coming.

        Returns:
            bytes: Them.

        Raises:
            CaptureError: If the peer went away first.
        """
        data = self._reader.read(count)
        if data is None or len(data) != count:
            raise CaptureError("the debugging connection ended mid-message")
        return data

    def _send_control(self, opcode: int, payload: bytes) -> None:
        """
        Send a masked control frame.

        Args:
            opcode: The control opcode.
            payload: At most 125 bytes, per the protocol.
        """
        mask = secrets.token_bytes(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._sock.sendall(
            bytes([0x80 | opcode, 0x80 | len(payload)]) + mask + masked
        )

    def close(self) -> None:
        """Shut the socket down, ignoring a peer that has already gone."""
        try:
            self._send_control(self.OP_CLOSE, b"")
        except OSError:
            pass
        try:
            self._reader.close()
            self._sock.close()
        except OSError:
            pass


class DevTools:
    """
    A CDP session against one page target.

    No domain is enabled, which means Chrome sends no unsolicited events and a
    command's reply is nearly always the next message on the wire. Any event
    that does arrive is discarded while waiting for the matching id, so the
    session cannot be knocked out of step by one.

    Attributes:
        _ws: The websocket to the page target.
        _next_id: The id for the next command.
    """

    def __init__(self, ws_url: str):
        """
        Args:
            ws_url: The page target's ``webSocketDebuggerUrl``.
        """
        self._ws = WebSocket(ws_url)
        self._next_id = 0

    def call(self, method: str, params: dict = None) -> dict:
        """
        Send one command and wait for its reply.

        Args:
            method: The CDP method, e.g. ``Page.captureScreenshot``.
            params: Its parameters.

        Returns:
            dict: The ``result`` object.

        Raises:
            CaptureError: If Chrome answered with an error.
        """
        self._next_id += 1
        message_id = self._next_id
        self._ws.send_text(
            json.dumps({"id": message_id, "method": method, "params": params or {}})
        )
        while True:
            message = json.loads(self._ws.recv_text())
            if message.get("id") != message_id:
                continue  # An event, or a reply nobody is waiting for any more.
            if "error" in message:
                error = message["error"]
                raise CaptureError(
                    f"{method} failed: {error.get('message', error)}"
                )
            return message.get("result", {})

    def evaluate(self, expression: str):
        """
        Evaluate JavaScript in the page and return its value.

        Args:
            expression: An expression yielding a JSON-serializable value.

        Returns:
            The value, or None if the expression produced undefined.

        Raises:
            CaptureError: If the expression threw.
        """
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            text = detail.get("exception", {}).get("description") or detail.get("text")
            raise CaptureError(f"page script failed: {text}")
        return result.get("result", {}).get("value")

    def close(self) -> None:
        """Close the session."""
        self._ws.close()


# --------------------------------------------------------------------------
# Paths, names and the server
# --------------------------------------------------------------------------


def windows_path(path: str) -> str:
    """
    Put a path into the form a Windows process understands.

    The script is launched from a WSL shell, so its path arguments arrive in
    WSL's form while everything that consumes them - the server, Chrome - is a
    Windows process.

    Args:
        path: A path in either form.

    Returns:
        str: The Windows form. ``/mnt/c/src/x`` becomes ``C:\\src\\x``; a path
        that is already a Windows one, or that has no drive to map, is returned
        unchanged apart from separators.
    """
    match = re.match(r"^/mnt/([a-zA-Z])(/.*)?$", path)
    if match:
        drive = match.group(1).upper()
        rest = (match.group(2) or "/").replace("/", "\\")
        return f"{drive}:{rest}"
    return path


def scratch_dir(prefix: str) -> str:
    """
    Make a fresh scratch directory inside the repository's ``.scratch/``.

    ``REPO_ROOT`` is resolved from this file, which the Windows venv sees as
    ``C:\\src\\pairwise_ranking\\scripts``, so the directory is already in the
    Windows form the server and Chrome need. The caller removes it.

    Args:
        prefix: The start of the directory's name.

    Returns:
        str: The new directory's path.
    """
    SCRATCH_ROOT.mkdir(exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=SCRATCH_ROOT)


def slugify(path: str) -> str:
    """
    Turn an app path into a file-name fragment.

    Args:
        path: The app path, possibly with a query string.

    Returns:
        str: A lowercase hyphenated slug. ``/`` becomes ``root`` so that the
        home screen's captures are named rather than nameless.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", path.strip("/")).strip("-").lower()
    return slug or "root"


def parse_target(argument: str) -> tuple:
    """
    Read one positional argument.

    Args:
        argument: Either ``/some/path`` or ``label=/some/path``.

    Returns:
        tuple: ``(label, path)``.

    Raises:
        CaptureError: If the path is not a path.
    """
    label, separator, path = argument.partition("=")
    if not separator:
        label, path = slugify(argument), argument
    if not path.startswith("/"):
        raise CaptureError(
            f"{argument!r} is not an app path; write it with a leading slash, "
            "e.g. register=/ or items=/projects/demo/items"
        )
    return label, path


def parse_size(argument: str) -> tuple:
    """
    Read a ``--size`` value.

    Args:
        argument: ``WIDTHxHEIGHT``, e.g. ``390x844``.

    Returns:
        tuple: ``(width, height)``.

    Raises:
        argparse.ArgumentTypeError: If it is not two positive numbers.
    """
    match = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", argument)
    if not match:
        raise argparse.ArgumentTypeError(
            f"expected a size like 390x844, got {argument!r}"
        )
    width, height = int(match.group(1)), int(match.group(2))
    if width < 1 or height < 1:
        raise argparse.ArgumentTypeError(f"{argument!r} is not a usable size")
    return width, height


def with_theme(url: str, theme: str) -> str:
    """
    Add the theme override to a URL.

    Args:
        url: The URL to capture.
        theme: ``light`` or ``dark``.

    Returns:
        str: The URL with ``theme=`` appended to its query, preserving whatever
        query the caller already asked for.
    """
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k != "theme"] + [("theme", theme)]
    return urllib.parse.urlunsplit(
        parts._replace(query=urllib.parse.urlencode(query))
    )


def start_server(data_dir: str, port: int) -> subprocess.Popen:
    """
    Boot the web app and wait until it answers.

    Args:
        data_dir: The ``PAIRRANK_DATA_DIR`` to serve, in Windows form.
        port: The port to bind.

    Returns:
        subprocess.Popen: The running server, for the caller to terminate.

    Raises:
        CaptureError: If it exits, or does not answer, within the timeout.
    """
    environment = dict(os.environ)
    environment.update(
        {
            "PAIRRANK_DATA_DIR": data_dir,
            "PAIRRANK_PORT": str(port),
            # Set so the boot log is not dominated by the "no key configured"
            # warning; nothing in a capture run depends on the sessions.
            "PAIRRANK_SECRET_KEY": secrets.token_urlsafe(32),
            "PAIRRANK_LOG_LEVEL": "WARNING",
        }
    )
    # sys.executable is the Windows venv's python, because that is what runs
    # this script; the server therefore inherits the same interpreter and the
    # same site-packages without any of it being spelled out here.
    process = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "web_main.py")],
        cwd=str(REPO_ROOT),
        env=environment,
    )

    health_url = f"http://127.0.0.1:{port}/healthz"
    deadline = time.monotonic() + SERVER_BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CaptureError(
                f"the server exited with status {process.returncode} before it "
                f"answered {health_url} - is port {port} already in use?"
            )
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return process
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(SERVER_POLL_INTERVAL_S)

    stop_process(process)
    raise CaptureError(
        f"the server did not answer {health_url} within "
        f"{SERVER_BOOT_TIMEOUT_S:.0f}s"
    )


def free_port() -> int:
    """
    Find a port nothing is listening on.

    Returns:
        int: A port number, for Chrome's debugging endpoint. Asked for rather
        than fixed so that two capture runs at once do not collide.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_chrome(profile_dir: str) -> tuple:
    """
    Start headless Chrome and attach to its first page.

    Args:
        profile_dir: A scratch user-data directory, in Windows form. A fresh
            one per run keeps a previously opened tab, a restored session or a
            remembered theme out of the captures.

    Returns:
        tuple: ``(process, DevTools)``.

    Raises:
        CaptureError: If Chrome is missing, or never offers a page target.
    """
    if not CHROME.exists():
        raise CaptureError(f"Chrome is not where this expects it: {CHROME}")

    port = free_port()
    process = subprocess.Popen(
        [
            str(CHROME),
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-gpu",
            # Scrollbars are chrome, not design, and on Windows they eat 15 px
            # off the layout width, which would make every capture narrower
            # than it claims.
            "--hide-scrollbars",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + CHROME_BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CaptureError(
                f"Chrome exited with status {process.returncode} on startup"
            )
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=2
            ) as response:
                targets = json.load(response)
            pages = [
                t
                for t in targets
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl")
            ]
            if pages:
                devtools = DevTools(pages[0]["webSocketDebuggerUrl"])
                # Page has to be enabled before a new-document script sticks.
                devtools.call("Page.enable")
                devtools.call(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": QUIET_PROBE},
                )
                # A headless window is not the focused window, so
                # document.hasFocus() is false, nothing matches :focus, and no
                # capture can show a focus ring - including the ring on the
                # field a callout has just put the caret in. This tells the
                # renderer to treat the page as focused, which is the state a
                # person looking at this screen would be in.
                devtools.call(
                    "Emulation.setFocusEmulationEnabled", {"enabled": True}
                )
                return process, devtools
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(SERVER_POLL_INTERVAL_S)

    stop_process(process)
    raise CaptureError(
        f"Chrome did not offer a debuggable page within {CHROME_BOOT_TIMEOUT_S:.0f}s"
    )


def stop_process(process: subprocess.Popen) -> None:
    """
    End a child process, politely and then not.

    Args:
        process: The child. Already-dead children are fine.
    """
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


# --------------------------------------------------------------------------
# Capturing
# --------------------------------------------------------------------------


def png_size(data: bytes) -> tuple:
    """
    Read a PNG's pixel dimensions out of its header.

    Args:
        data: The whole file.

    Returns:
        tuple: ``(width, height)``.

    Raises:
        CaptureError: If it is not a PNG.
    """
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE):
        raise CaptureError("the browser returned something that is not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def capture(devtools: DevTools, url: str, width: int, height: int) -> tuple:
    """
    Load one URL at one viewport and photograph it.

    Args:
        devtools: The attached page session.
        url: The URL to load, theme and all.
        width: The CSS pixel width the page must lay out at.
        height: The CSS pixel height.

    Returns:
        tuple: ``(png_bytes, measured_width)``. The measured width is handed
        back rather than assumed so the log line quotes what the page actually
        did, not what it was told to do.

    Raises:
        CaptureError: If the page never became ready, or laid out at a width
            other than the one asked for. The second is the whole reason this
            function reads anything back: Chrome's headless window will not go
            below 500 CSS px, so a capture that quietly came out at 500 would
            be filed as a phone screenshot and believed.
    """
    devtools.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
            "screenWidth": width,
            "screenHeight": height,
        },
    )
    devtools.call("Page.navigate", {"url": url})

    deadline = time.monotonic() + PAGE_READY_TIMEOUT_S
    while True:
        # Always a promise, because CDP's awaitPromise is only reliable when
        # the expression really is one.
        ready = devtools.evaluate(
            "document.readyState === 'complete'"
            " ? document.fonts.ready.then(() => true)"
            " : Promise.resolve(false)"
        )
        if ready is True:
            break
        if time.monotonic() > deadline:
            raise CaptureError(
                f"{url} was not ready within {PAGE_READY_TIMEOUT_S:.0f}s"
            )
        time.sleep(PAGE_POLL_INTERVAL_S)

    # Ready is not finished: the callout is fetched after the load event. The
    # counter is asserted rather than read defensively, because a missing one
    # would silently put the shutter back on the luck it was taken off.
    if devtools.evaluate("typeof window.__capturePending") != "number":
        raise CaptureError(
            f"the in-flight request counter never installed at {url}; without "
            "it a capture cannot be trusted to have its callout in it"
        )
    deadline = time.monotonic() + QUIET_TIMEOUT_S
    while devtools.evaluate("window.__capturePending"):
        if time.monotonic() > deadline:
            raise CaptureError(
                f"{url} still had a request in flight after "
                f"{QUIET_TIMEOUT_S:.0f}s"
            )
        time.sleep(PAGE_POLL_INTERVAL_S)
    time.sleep(SETTLE_S)

    missing = devtools.evaluate(CALLOUT_CHECK)
    if missing:
        raise CaptureError(
            f"no callout at {url}: the row {missing} is selected and asks for "
            "one, but #row-callout is empty"
        )
    missing = devtools.evaluate(COMPARE_CHECK)
    if missing:
        raise CaptureError(f"not a whole pair at {url}: the sheet has {missing}")
    missing = devtools.evaluate(SETTINGS_CHECK)
    if missing:
        raise CaptureError(f"not a whole settings sheet at {url}: it has {missing}")

    actual = devtools.evaluate("window.innerWidth")
    if actual != width:
        raise CaptureError(
            f"viewport width mismatch at {url}: asked for {width} CSS px, "
            f"the page laid out at {actual}"
        )

    result = devtools.call(
        "Page.captureScreenshot",
        {"format": "png", "captureBeyondViewport": False},
    )
    data = base64.b64decode(result["data"])
    shot_width, shot_height = png_size(data)
    if (shot_width, shot_height) != (width, height):
        raise CaptureError(
            f"screenshot size mismatch at {url}: asked for {width}x{height}, "
            f"got {shot_width}x{shot_height}"
        )
    return data, actual


def run(args: argparse.Namespace) -> int:
    """
    Boot what is needed, take every capture, and tear it all down.

    Args:
        args: The parsed command line.

    Returns:
        int: 0 when every capture was taken and verified.

    Raises:
        CaptureError: On the first capture that could not be trusted. The
            teardown still happens; the remaining captures do not, because a
            half-broken harness should be fixed before more images are filed
            under it.
    """
    targets = [parse_target(argument) for argument in args.paths]
    out_dir = Path(windows_path(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    server = None
    chrome = None
    devtools = None
    profile_dir = scratch_dir("pairrank-capture-")

    try:
        if args.base_url:
            base_url = args.base_url.rstrip("/")
            print(f"{PROGRAM}: capturing the server already at {base_url}")
        else:
            data_dir = windows_path(args.data_dir)
            if not Path(data_dir).is_dir():
                raise CaptureError(
                    f"no such data directory: {data_dir} (it has to be under "
                    "/mnt/... - the server is a Windows process and cannot see "
                    "WSL's own filesystem)"
                )
            server = start_server(data_dir, args.port)
            base_url = f"http://127.0.0.1:{args.port}"
            print(f"{PROGRAM}: serving {data_dir} at {base_url}")

        chrome, devtools = start_chrome(profile_dir)

        for label, path in targets:
            for width, height in args.sizes:
                for theme in args.themes:
                    url = with_theme(base_url + path, theme)
                    data, measured = capture(devtools, url, width, height)
                    destination = out_dir / f"web-{label}-{width}-{theme}.png"
                    destination.write_bytes(data)
                    print(
                        f"{PROGRAM}: {destination.name} "
                        f"({width}x{height}, innerWidth {measured}, "
                        f"{len(data)} bytes)"
                    )
        return 0
    finally:
        if devtools is not None:
            devtools.close()
        if chrome is not None:
            stop_process(chrome)
        if server is not None:
            stop_process(server)
        shutil.rmtree(profile_dir, ignore_errors=True)


def main(argv: list = None) -> int:
    """
    Parse the command line and run.

    Args:
        argv: Arguments, defaulting to the process's.

    Returns:
        int: The exit status - 0 on success, 1 on a capture that could not be
        trusted.
    """
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Capture the running web app at review widths in both themes.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="[LABEL=]PATH",
        help="app paths to capture, e.g. register=/ or items=/projects/demo/items",
    )
    parser.add_argument(
        "--data-dir",
        help="the PAIRRANK_DATA_DIR to boot against (required unless --base-url)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="where the PNGs go (default: .impeccable/review)",
    )
    parser.add_argument(
        "--size",
        dest="sizes",
        action="append",
        type=parse_size,
        metavar="WxH",
        help="a viewport to capture, repeatable (default: 390x844 1280x900 1920x1080)",
    )
    parser.add_argument(
        "--theme",
        dest="themes",
        action="append",
        choices=("light", "dark"),
        help="a theme to capture, repeatable (default: both)",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="dev port (default: 8099)"
    )
    parser.add_argument(
        "--base-url",
        help="capture an already-running server instead of booting one",
    )
    args = parser.parse_args(argv)

    args.sizes = args.sizes or list(DEFAULT_SIZES)
    args.themes = args.themes or list(DEFAULT_THEMES)
    if not args.base_url and not args.data_dir:
        parser.error("--data-dir is required unless --base-url is given")

    try:
        return run(args)
    except CaptureError as e:
        print(f"{PROGRAM}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
