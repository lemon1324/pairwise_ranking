"""Tests for the request filters in front of every route.

These go through the whole application rather than through each middleware on
its own: what matters is what a browser, a proxy or the container's
HEALTHCHECK gets back, and that depends on the order
:func:`~src.web.app.create_app` stacks the filters in as much as on any one of
them.
"""

import dataclasses
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

import web_main
from src.web.app import (
    MAX_REQUEST_BYTES,
    SECURITY_HEADERS,
    STATIC_MOUNT,
    create_app,
)
from src.web.config import ANY_HOST
from src.web.routes.projects import MAX_IMPORT_BYTES
from tests.test_web_projects import config_for, project_data, silence


class MiddlewareTestCase(unittest.TestCase):
    """Base case giving each test an application over a temporary directory."""

    root_path = ""

    # The configured allowlist, on top of loopback. TestClient's own host
    # name, so requests that do not set one get through.
    allowed_hosts = ("testserver",)

    def setUp(self):
        """Build an application over an empty data directory."""
        silence(
            self, "src.web.registry", "src.web.app", "src.web.routes.projects"
        )
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        self.app = self.build_app()
        self.client = TestClient(
            self.app, root_path=self.root_path, raise_server_exceptions=False
        )

    def tearDown(self):
        """Remove the data directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def build_app(self):
        """
        Build the application under test.

        Returns:
            FastAPI: An application allowing :attr:`allowed_hosts`.
        """
        config = dataclasses.replace(
            config_for(self.data_dir, self.root_path),
            allowed_hosts=self.allowed_hosts,
        )
        return create_app(config)

    def create(self, name: str = "Keyswitches", **headers):
        """
        Post the new-project form.

        Args:
            name: The project name.
            **headers: Request headers, with underscores for dashes.

        Returns:
            Response: The response, without following a redirect.
        """
        return self.client.post(
            "/projects/new",
            data={"name": name},
            headers={k.replace("_", "-"): v for k, v in headers.items()},
            follow_redirects=False,
        )

    def project_files(self) -> list:
        """
        List the project files in the data directory.

        Returns:
            list: Their names, sorted.
        """
        return sorted(p.name for p in self.data_dir.glob("*.pairrank"))


class TestAllowedHosts(MiddlewareTestCase):
    """Test cases for refusing requests addressed to a name the server is not."""

    allowed_hosts = ("nas.lan", "*.example.lan")

    def test_a_listed_host_is_served(self):
        """Test that a name on the list reaches the page."""
        for host in ("nas.lan", "NAS.lan:8080", "rank.example.lan"):
            with self.subTest(host=host):
                response = self.client.get("/", headers={"Host": host})
                self.assertEqual(response.status_code, 200)

    def test_an_unlisted_host_is_refused(self):
        """Test that a rebinding page's own name gets nowhere."""
        for host in (
            "attacker.example",
            "nas.lan.attacker.example",
            "example.lan",
            "badexample.lan",
            "testserver",
            "",
        ):
            with self.subTest(host=host):
                response = self.client.get("/healthz", headers={"Host": host})
                self.assertEqual(response.status_code, 400)
                self.assertIn("Invalid host header", response.text)

    def test_loopback_is_always_allowed(self):
        """Test that the HEALTHCHECK and the CI smoke test are never refused."""
        for host in ("localhost", "127.0.0.1:8080", "[::1]:8080", "LOCALHOST"):
            with self.subTest(host=host):
                response = self.client.get("/healthz", headers={"Host": host})
                self.assertEqual(response.status_code, 200)

    def test_a_refused_host_changes_nothing(self):
        """Test that a post under the wrong name never reaches the route."""
        response = self.create(host="attacker.example")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.project_files(), [])


class TestUnsetAllowedHosts(MiddlewareTestCase):
    """Test cases for a server nobody has given a list to."""

    allowed_hosts = ()

    def test_only_loopback_is_served(self):
        """Test that the check fails closed."""
        self.assertEqual(self.client.get("/healthz").status_code, 400)
        self.assertEqual(
            self.client.get("/healthz", headers={"Host": "nas.lan"}).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/healthz", headers={"Host": "127.0.0.1:8080"}
            ).status_code,
            200,
        )


class TestAnyHost(MiddlewareTestCase):
    """Test cases for an operator who has switched the check off."""

    allowed_hosts = (ANY_HOST,)

    def test_every_host_is_served(self):
        """Test that a lone wildcard lets any name through."""
        response = self.client.get("/healthz", headers={"Host": "anything.example"})

        self.assertEqual(response.status_code, 200)


class TestCrossSiteRequests(MiddlewareTestCase):
    """Test cases for refusing changes a page on another site asked for."""

    def test_a_cross_site_post_is_refused(self):
        """Test that a hidden form on another site cannot create a project."""
        for site in ("cross-site", "same-site"):
            with self.subTest(site=site):
                response = self.create(
                    sec_fetch_site=site, origin="http://evil.example"
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.project_files(), [])

    def test_a_mismatched_origin_is_refused_without_fetch_metadata(self):
        """Test that an older browser's Origin is compared with the host."""
        for origin in (
            "http://evil.example",
            "http://evil.example:8080",
            "http://testserver.evil.example",
            "http://eviltestserver",
            "null",
        ):
            with self.subTest(origin=origin):
                self.assertEqual(self.create(origin=origin).status_code, 403)
        self.assertEqual(self.project_files(), [])

    def test_a_port_mismatch_is_refused_when_the_host_has_a_port(self):
        """Test that a Host with a port is matched port and all."""
        for host, origin in (
            ("testserver:8080", "http://testserver"),
            ("testserver:8080", "http://testserver:9090"),
            ("[::1]:8080", "http://[::1]:9090"),
        ):
            with self.subTest(host=host, origin=origin):
                self.assertEqual(
                    self.create(host=host, origin=origin).status_code, 403
                )
        self.assertEqual(self.project_files(), [])

    def test_a_host_without_a_port_matches_its_name_on_any_port(self):
        """Test that a proxy dropping the port from Host keeps forms working."""
        for name, host, origin in (
            ("A", "testserver", "http://testserver:1880"),
            ("B", "TestServer", "https://testserver:8443"),
            ("C", "[::1]", "http://[::1]:1880"),
            ("D", "testserver:8080", "http://TESTSERVER:8080"),
        ):
            with self.subTest(host=host, origin=origin):
                self.assertEqual(
                    self.create(name, host=host, origin=origin).status_code, 303
                )
        self.assertEqual(
            self.project_files(),
            ["A.pairrank", "B.pairrank", "C.pairrank", "D.pairrank"],
        )

    def test_a_host_without_a_port_still_refuses_another_name(self):
        """Test that dropping the port compares names, not prefixes."""
        for host, origin in (
            ("testserver", "http://evil.example:1880"),
            ("[::1]", "http://[::2]:1880"),
            ("[::1]", "http://localhost:1880"),
        ):
            with self.subTest(host=host, origin=origin):
                self.assertEqual(
                    self.create(host=host, origin=origin).status_code, 403
                )

    def test_a_same_origin_post_is_served(self):
        """Test that the application's own forms still work."""
        self.assertEqual(self.create("A", sec_fetch_site="same-origin").status_code, 303)
        self.assertEqual(self.create("B", sec_fetch_site="none").status_code, 303)
        self.assertEqual(self.create("C", origin="http://testserver").status_code, 303)
        self.assertEqual(self.project_files(), ["A.pairrank", "B.pairrank", "C.pairrank"])

    def test_fetch_metadata_outranks_origin(self):
        """Test that a same-origin request is not refused over its Origin."""
        response = self.create(
            sec_fetch_site="same-origin", origin="https://proxy.example"
        )

        self.assertEqual(response.status_code, 303)

    def test_a_post_with_neither_header_is_served(self):
        """Test that scripts and old browsers are not locked out."""
        self.assertEqual(self.create().status_code, 303)

    def test_a_cross_site_get_is_served(self):
        """Test that following a link from elsewhere still opens the page."""
        response = self.client.get(
            "/", headers={"Sec-Fetch-Site": "cross-site", "Origin": "http://evil.example"}
        )

        self.assertEqual(response.status_code, 200)


class TestCrossSiteRequestsUnderARootPath(MiddlewareTestCase):
    """Test cases for the check behind a proxy that serves a subpath."""

    root_path = "/rank"
    allowed_hosts = ("rank.example.lan",)

    def test_the_proxied_origin_matches_the_forwarded_host(self):
        """Test that a proxy keeping the Host header keeps forms working."""
        response = self.create(
            host="rank.example.lan", origin="https://rank.example.lan"
        )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["location"].startswith("/rank/"))

    def test_a_cross_site_post_is_still_refused(self):
        """Test that the prefix does not open a way round the check."""
        response = self.create(
            host="rank.example.lan", origin="https://evil.example"
        )

        self.assertEqual(response.status_code, 403)


class TestBodySizeLimit(MiddlewareTestCase):
    """
    Test cases for refusing request bodies no form could need.

    The real limit is 33 MiB, so most of these patch it down rather than
    upload past it; the declared-length tests use the real one, since a
    Content-Length is refused before any body is sent.
    """

    # Small enough to cross cheaply, large enough for a real multipart form.
    SMALL_LIMIT = 4096

    def project_bytes(self) -> bytes:
        """
        Build a small, valid project file to import.

        Returns:
            bytes: Its contents.
        """
        return json.dumps(project_data(name="Imported")).encode()

    def import_project(self, raw: bytes, file_name: str = "Imported.pairrank"):
        """
        Post the import form.

        Args:
            raw: The uploaded file's bytes.
            file_name: The name it is uploaded under.

        Returns:
            Response: The response, without following a redirect.
        """
        return self.client.post(
            "/projects/import",
            files={"file": (file_name, raw, "application/json")},
            follow_redirects=False,
        )

    def test_an_oversized_declared_length_is_refused_unread(self):
        """Test that a Content-Length past the limit never reaches a route."""
        too_long = str(MAX_REQUEST_BYTES + 1)
        for path in ("/projects/new", "/projects/import"):
            with self.subTest(path=path):
                response = self.client.post(
                    path,
                    content=b"name=Big",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Content-Length": too_long,
                    },
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 413)
        self.assertEqual(self.project_files(), [])

    def test_the_limit_leaves_room_for_the_largest_import(self):
        """Test that the body limit sits above the import route's own."""
        self.assertGreater(MAX_REQUEST_BYTES, MAX_IMPORT_BYTES)

    def test_an_oversized_streamed_body_is_refused(self):
        """Test that a body with no declared length is counted as it arrives."""

        def chunks():
            """Yield a form body twice the limit, a kilobyte at a time."""
            yield b"name="
            for _ in range(2 * self.SMALL_LIMIT // 1024):
                yield b"x" * 1024

        with patch("src.web.app.MAX_REQUEST_BYTES", self.SMALL_LIMIT):
            client = TestClient(self.build_app(), raise_server_exceptions=False)
        response = client.post(
            "/projects/new",
            content=chunks(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 413)
        # Found while the form was being parsed, so the application's own
        # error page answers rather than the middleware's plain text.
        self.assertIn("request refused", response.text)
        self.assertEqual(self.project_files(), [])

    def test_an_oversized_streamed_upload_is_refused(self):
        """Test that a chunked multipart import stops at the limit too."""
        boundary = "limit-test-boundary"

        def chunks():
            """Yield one file part twice the limit, a kilobyte at a time."""
            yield (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"Big.pairrank\"\r\nContent-Type: application/json\r\n\r\n"
            ).encode()
            for _ in range(2 * self.SMALL_LIMIT // 1024):
                yield b" " * 1024
            yield f"\r\n--{boundary}--\r\n".encode()

        with patch("src.web.app.MAX_REQUEST_BYTES", self.SMALL_LIMIT):
            client = TestClient(self.build_app(), raise_server_exceptions=False)
        response = client.post(
            "/projects/import",
            content=chunks(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.project_files(), [])

    def test_an_oversized_upload_is_refused(self):
        """Test that a multipart import past the limit is turned away."""
        with patch("src.web.app.MAX_REQUEST_BYTES", self.SMALL_LIMIT):
            self.client = TestClient(self.build_app(), raise_server_exceptions=False)

        response = self.import_project(b" " * (2 * self.SMALL_LIMIT))

        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.project_files(), [])

    def test_a_normal_import_still_works(self):
        """Test that the limit is no obstacle to a real project."""
        response = self.import_project(self.project_bytes())

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.project_files(), ["Imported.pairrank"])

    def test_a_body_under_the_limit_reaches_the_import_check(self):
        """Test that the route's own size message still answers what gets through."""
        with patch("src.web.app.MAX_REQUEST_BYTES", self.SMALL_LIMIT):
            self.client = TestClient(self.build_app(), raise_server_exceptions=False)

        with patch("src.web.routes.projects.MAX_IMPORT_BYTES", 64):
            response = self.import_project(b" " * 1024)

        self.assertEqual(response.status_code, 303)
        self.assertIn("error=size", response.headers["location"])
        self.assertEqual(self.project_files(), [])


class TestSecurityHeaders(MiddlewareTestCase):
    """Test cases for the hardening headers on every response."""

    def assert_hardened(self, response):
        """
        Check one response carries every security header.

        Args:
            response: The response to check.
        """
        for name, value in SECURITY_HEADERS.items():
            self.assertEqual(response.headers.get(name), value, name)

    def test_a_page_is_hardened(self):
        """Test that the register carries the headers."""
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assert_hardened(response)

    def test_the_policy_only_forbids_framing(self):
        """Test that the CSP does not also block the templates' inline scripts."""
        policy = SECURITY_HEADERS["Content-Security-Policy"]

        self.assertEqual(policy, "frame-ancestors 'none'")

    def test_a_static_file_is_hardened(self):
        """Test that the stylesheets carry the headers too."""
        response = self.client.get(f"{STATIC_MOUNT}/css/sheet.css")

        self.assertEqual(response.status_code, 200)
        self.assert_hardened(response)

    def test_an_error_page_is_hardened(self):
        """Test that the not-found page carries the headers."""
        response = self.client.get("/no-such-page")

        self.assertEqual(response.status_code, 404)
        self.assert_hardened(response)

    def test_the_filters_refusals_are_hardened(self):
        """Test that the 400, 403 and 413 answered ahead of the app carry them."""
        refused_host = self.client.get("/", headers={"Host": "attacker.example"})
        cross_site = self.create(sec_fetch_site="cross-site")
        too_large = self.client.post(
            "/projects/new",
            content=b"name=x",
            headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)},
        )

        for response, status in ((refused_host, 400), (cross_site, 403), (too_large, 413)):
            with self.subTest(status=status):
                self.assertEqual(response.status_code, status)
                self.assert_hardened(response)

    def test_a_header_a_route_sets_is_left_alone(self):
        """Test that the headers are defaults rather than overrides."""

        @self.app.get("/framable")
        async def framable() -> PlainTextResponse:
            """Answer with a framing policy of its own."""
            return PlainTextResponse(
                "ok", headers={"X-Frame-Options": "SAMEORIGIN"}
            )

        response = self.client.get("/framable")

        self.assertEqual(response.headers["x-frame-options"], "SAMEORIGIN")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")


class TestServerHeader(unittest.TestCase):
    """Test cases for what web_main hands uvicorn."""

    def test_uvicorn_is_told_not_to_name_itself(self):
        """Test that responses go out without a Server header."""
        with patch("web_main.configure_logging"), patch(
            "web_main.load_config", return_value=config_for(Path("unused"))
        ), patch("web_main.create_app"), patch("web_main.uvicorn.run") as run:
            self.assertEqual(web_main.main(), 0)

        self.assertIs(run.call_args.kwargs["server_header"], False)
        self.assertEqual(run.call_args.kwargs["host"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
