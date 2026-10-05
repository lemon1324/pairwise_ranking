"""Tests for the request filters in front of every route.

These go through the whole application rather than through each middleware on
its own: what matters is what a browser, a proxy or the container's
HEALTHCHECK gets back, and that depends on the order
:func:`~src.web.app.create_app` stacks the filters in as much as on any one of
them.
"""

import dataclasses
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.web.app import create_app
from src.web.config import ANY_HOST
from tests.test_web_projects import config_for, silence


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
            "http://testserver:8080",
            "http://testserver.evil.example",
            "null",
        ):
            with self.subTest(origin=origin):
                self.assertEqual(self.create(origin=origin).status_code, 403)
        self.assertEqual(self.project_files(), [])

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


if __name__ == "__main__":
    unittest.main()
