"""Route-level tests for the web application's skeleton.

The error-page tests need a route that opens a project and can fail to, without
being about any one screen. :func:`probe_route` attaches a route that does
nothing but depend on :func:`~src.web.deps.get_session`, which reads the file
as it is now, as every screen's GET does through ``registry.open_fresh()``.
That keeps these tests about the wiring under test - the dependency, the
exceptions it raises, the handlers, the templates - rather than about a route
written to make a test pass.
"""

import json
import logging
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
# uvicorn's own table, read rather than restated: the point of the log-level
# test is that the two agree, which a copy of the list here could not show.
from uvicorn.config import LOG_LEVELS

from src.app.session import ProjectSession
from src.data import format_version
from src.data.format_version import CURRENT_FORMAT_VERSION, FORMAT_VERSION_KEY
from src.data.project_storage import ProjectStorage
from src.web.app import (
    DAMAGED_STATUS,
    NEWER_FORMAT_STATUS,
    STATIC_MOUNT,
    create_app,
)
from src.web.config import (
    AUTH_MODE_VAR,
    DATA_DIR_VAR,
    DEFAULT_DATA_DIR,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    LOG_LEVEL_VAR,
    PORT_VAR,
    ROOT_PATH_VAR,
    SECRET_KEY_VAR,
    UVICORN_LOG_LEVELS,
    WebConfig,
    load_config,
)
from src.web.deps import LOCAL_PRINCIPAL, Principal, get_current_user, get_session


def config_for(data_dir: Path, root_path: str = "") -> WebConfig:
    """
    Build a configuration pointing at a temporary data directory.

    Args:
        data_dir: The directory the application serves projects from.
        root_path: The subpath a reverse proxy would serve it under.

    Returns:
        WebConfig: A configuration with a fixed key, so nothing in a test run
        depends on a generated one.
    """
    return WebConfig(
        data_dir=data_dir,
        port=8099,
        root_path=root_path,
        secret_key="test-key-not-a-secret",
        secret_key_generated=False,
        auth_mode="none",
        log_level="CRITICAL",
    )


def silence(case: unittest.TestCase, *names: str) -> None:
    """
    Keep the application's own warnings out of the test run's output.

    Several of these tests exercise failures the application is right to warn
    about - a refused project id, a damaged file, an unset session key - and an
    untouched root logger prints every one of them. Silencing is per logger and
    undone afterwards, and ``assertLogs`` still sees the records, so no test
    that cares about a warning is affected.

    Args:
        case: The test case to attach the cleanup to.
        *names: The loggers to quieten.
    """
    for name in names:
        logger = logging.getLogger(name)
        case.addCleanup(setattr, logger, "propagate", logger.propagate)
        sink = logging.NullHandler()
        case.addCleanup(logger.removeHandler, sink)
        logger.addHandler(sink)
        logger.propagate = False


def probe_route(app: FastAPI) -> None:
    """
    Attach the smallest possible project route to an application.

    Args:
        app: The application to attach it to.
    """

    @app.get("/probe/{project_id}")
    async def probe(
        session: ProjectSession = Depends(get_session),
        user: Principal = Depends(get_current_user),
    ) -> PlainTextResponse:
        """Report who is asking and what project they reached."""
        return PlainTextResponse(f"{user.name}:{session.project.name}")


class WebAppTestCase(unittest.TestCase):
    """Base case giving each test an application over a temporary directory."""

    root_path = ""

    def setUp(self):
        """Build an application over an empty data directory."""
        silence(self, "src.web.registry", "src.web.app")
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        self.app = create_app(config_for(self.data_dir, self.root_path))
        probe_route(self.app)
        self.client = TestClient(self.app)

    def tearDown(self):
        """Remove the data directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_raw(self, file_name: str, data) -> Path:
        """
        Write a project file by hand.

        Args:
            file_name: The name to write it under.
            data: The value to serialize, or a str to write verbatim.

        Returns:
            Path: The file written.
        """
        path = self.data_dir / file_name
        path.write_text(
            data if isinstance(data, str) else json.dumps(data), encoding="utf-8"
        )
        return path


class TestHealth(WebAppTestCase):
    """Test cases for the endpoint the container's healthcheck calls."""

    def test_healthz_is_ok(self):
        """Test that a running process reports itself up."""
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_healthz_does_not_need_the_data_directory(self):
        """Test that the healthcheck answers with nothing to serve."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        self.assertEqual(self.client.get("/healthz").status_code, 200)


class TestNotFound(WebAppTestCase):
    """Test cases for addresses that lead nowhere."""

    def test_an_unknown_path_renders_the_not_found_page(self):
        """Test that a bad URL is a page rather than a JSON detail."""
        response = self.client.get("/no-such-sheet")

        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Not found", response.text)
        self.assertNotIn('{"detail"', response.text)

    def test_an_unknown_project_renders_the_not_found_page(self):
        """Test that a project that is not there reads the same way."""
        response = self.client.get("/probe/Missing.pairrank")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Not found", response.text)

    def test_a_traversal_id_renders_the_not_found_page(self):
        """Test that a name reaching out of the directory is refused."""
        for project_id in ("..%2Fsecrets.pairrank", "sub%5Cother.pairrank", "notes.txt"):
            with self.subTest(project_id=project_id):
                response = self.client.get(f"/probe/{project_id}")

                self.assertEqual(response.status_code, 404)
                self.assertIn("Not found", response.text)

    def test_the_not_found_page_offers_a_way_back(self):
        """Test that the error pages link home rather than dead-ending."""
        response = self.client.get("/no-such-sheet")

        self.assertIn('href="/"', response.text)


class TestErrorPagesUnderARootPath(WebAppTestCase):
    """Test cases for running behind a reverse proxy on a subpath."""

    root_path = "/rank"

    def test_the_way_back_carries_the_proxy_prefix(self):
        """Test that a link home does not escape the proxy's subpath."""
        response = self.client.get("/no-such-sheet")

        self.assertEqual(response.status_code, 404)
        self.assertIn('href="/rank/"', response.text)


class TestProjectFormatErrorPages(WebAppTestCase):
    """Test cases for the two ways a project file can be unusable.

    These are separate pages on purpose: a file written by a newer version of
    the application is intact and will open after an update, while a damaged
    one needs its backup. Telling a user the wrong one of those costs them a
    project.
    """

    def project_data(self, name="Tasting") -> dict:
        """
        Build a valid current-format project dictionary.

        Args:
            name: The project name to store.

        Returns:
            dict: The project data, ready to be written as JSON.
        """
        path = self.data_dir / "scratch.pairrank"
        ProjectStorage.create_new(name, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        path.unlink()
        return data

    def test_a_newer_format_file_needs_a_newer_application(self):
        """Test that a future format version gets its own page."""
        data = self.project_data()
        data[FORMAT_VERSION_KEY] = CURRENT_FORMAT_VERSION + 1
        self.write_raw("Future.pairrank", data)

        response = self.client.get("/probe/Future.pairrank")

        self.assertEqual(response.status_code, NEWER_FORMAT_STATUS)
        self.assertIn("newer version", response.text)
        self.assertIn(str(CURRENT_FORMAT_VERSION + 1), response.text)
        self.assertNotIn("damaged", response.text)

    def test_a_gap_in_the_upgrade_chain_is_damage_rather_than_a_newer_file(self):
        """
        Test that the other ProjectFormatError lands on the damaged page.

        Two subclasses, two pages, and only one of them was ever exercised
        through a route. UnsupportedUpgradeError arrives as the base class, and
        a handler registered for the base class is exactly what a later reorder
        of these lines could take away.
        """
        data = self.project_data()
        data[FORMAT_VERSION_KEY] = 1
        self.write_raw("Old.pairrank", data)

        # The gap is manufactured: every version this application has ever
        # written does have an upgrade step, which is the point of the chain.
        with patch.dict(format_version._UPGRADE_STEPS, clear=True):
            response = self.client.get("/probe/Old.pairrank")

        self.assertEqual(response.status_code, DAMAGED_STATUS)
        self.assertIn("damaged", response.text)
        self.assertNotIn("newer version", response.text)

    def test_a_corrupt_file_is_damaged(self):
        """Test that JSON that will not parse gets the other page."""
        self.write_raw("Broken.pairrank", "{ not json at all")

        response = self.client.get("/probe/Broken.pairrank")

        self.assertEqual(response.status_code, DAMAGED_STATUS)
        self.assertIn("damaged", response.text)
        self.assertNotIn("newer version", response.text)

    def test_the_damaged_page_points_at_the_backups(self):
        """Test that the page says what a user can actually do about it."""
        self.write_raw("Broken.pairrank", "{ not json at all")

        response = self.client.get("/probe/Broken.pairrank")

        self.assertIn(".pairrank.bak", response.text)

    def test_a_readable_project_reaches_the_route(self):
        """Test that the error paths have not swallowed the working one."""
        ProjectStorage.create_new("Tasting", self.data_dir / "Tasting.pairrank")

        response = self.client.get("/probe/Tasting.pairrank")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, f"{LOCAL_PRINCIPAL.name}:Tasting")


class TestTheSessionIsRead(WebAppTestCase):
    """Test cases for get_session reading the file as it is now, not the cache."""

    def setUp(self):
        """Open one project through the probe, so the registry caches it."""
        super().setUp()
        self.path = self.data_dir / "Tasting.pairrank"
        ProjectStorage.create_new("Tasting", self.path)
        self.assertEqual(self.client.get("/probe/Tasting.pairrank").status_code, 200)

    def test_a_change_made_elsewhere_is_seen(self):
        """Test that a file renamed by another program draws its new name."""
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["name"] = "Tasting, second flight"
        self.write_raw("Tasting.pairrank", data)

        response = self.client.get("/probe/Tasting.pairrank")

        self.assertEqual(response.text, f"{LOCAL_PRINCIPAL.name}:Tasting, second flight")

    def test_a_deleted_file_is_not_found(self):
        """Test that the cached project is not drawn once its file is gone."""
        self.path.unlink()

        response = self.client.get("/probe/Tasting.pairrank")

        self.assertEqual(response.status_code, 404)


class TestServerError(WebAppTestCase):
    """Test cases for the page a bug lands on."""

    def test_an_unhandled_error_renders_the_server_error_page(self):
        """Test that a route blowing up shows a page, not a traceback."""

        @self.app.get("/boom")
        async def boom() -> PlainTextResponse:
            """Fail the way a bug fails."""
            raise RuntimeError("something nobody anticipated")

        # The default client re-raises server exceptions, which is the right
        # default for a test suite and the wrong one for the single test that
        # is about what the user sees instead.
        client = TestClient(self.app, raise_server_exceptions=False)
        with self.assertLogs("src.web.app", "ERROR"):
            response = client.get("/boom")

        self.assertEqual(response.status_code, 500)
        self.assertIn("Something went wrong", response.text)
        self.assertNotIn("something nobody anticipated", response.text)


class TestAppWiring(WebAppTestCase):
    """Test cases for what the factory puts on the application."""

    def test_the_registry_serves_the_configured_directory(self):
        """Test that the app's registry is the one over the data directory."""
        self.assertEqual(self.app.state.registry.data_dir, self.data_dir)

    def test_the_session_middleware_issues_a_cookie(self):
        """Test that a route writing to the session gets a signed cookie back."""

        @self.app.get("/set")
        async def set_value(request: Request) -> PlainTextResponse:
            """Write to the session, which makes the middleware emit a cookie."""
            request.session["seen"] = True
            return PlainTextResponse("ok")

        response = self.client.get("/set")

        self.assertEqual(response.status_code, 200)
        self.assertIn("session", response.cookies)

    def test_the_current_user_is_the_fixed_local_principal(self):
        """Test that the auth seam answers with one principal, not a new one."""
        ProjectStorage.create_new("Tasting", self.data_dir / "Tasting.pairrank")

        first = self.client.get("/probe/Tasting.pairrank").text
        second = self.client.get("/probe/Tasting.pairrank").text

        self.assertEqual(first, second)
        self.assertEqual(LOCAL_PRINCIPAL.display_name, "Local user")

    def test_static_files_are_mounted(self):
        """
        Test that the mount phase 4b filled is answering.

        Asked for over a file the application ships rather than one written for
        the occasion: writing into the source tree fails on a read-only
        checkout, and a run killed mid-test leaves the probe behind.
        """
        response = self.client.get(f"{STATIC_MOUNT}/css/sheet.css")

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 0)
        self.assertIn("css", response.headers["content-type"])


class TestConfig(unittest.TestCase):
    """Test cases for reading the container's environment."""

    def setUp(self):
        """Quieten the warning most of these tests deliberately provoke."""
        silence(self, "src.web.config")

    def test_defaults_match_the_container(self):
        """Test that an empty environment is the shipped configuration."""
        config = load_config({})

        self.assertEqual(config.data_dir, Path(DEFAULT_DATA_DIR))
        self.assertEqual(config.port, DEFAULT_PORT)
        self.assertEqual(config.root_path, "")
        self.assertEqual(config.auth_mode, "none")

    def test_an_unset_secret_key_is_generated_with_a_warning(self):
        """Test that a missing key does not silently become a fixed one."""
        with self.assertLogs("src.web.config", "WARNING") as logged:
            config = load_config({})

        self.assertTrue(config.secret_key)
        self.assertTrue(config.secret_key_generated)
        self.assertIn(SECRET_KEY_VAR, logged.output[0])

    def test_two_generated_keys_differ(self):
        """Test that the generated key is random rather than a placeholder."""
        with self.assertLogs("src.web.config", "WARNING"):
            first = load_config({}).secret_key
            second = load_config({}).secret_key

        self.assertNotEqual(first, second)

    def test_a_configured_secret_key_is_used_as_given(self):
        """Test that a configured key is neither replaced nor warned about."""
        config = load_config({SECRET_KEY_VAR: "  a-real-key  "})

        self.assertEqual(config.secret_key, "a-real-key")
        self.assertFalse(config.secret_key_generated)

    def test_the_root_path_is_normalized(self):
        """Test that the slashes an operator writes do not matter."""
        for raw in ("/rank", "rank", "/rank/", "rank/"):
            with self.subTest(raw=raw):
                self.assertEqual(load_config({ROOT_PATH_VAR: raw}).root_path, "/rank")

    def test_a_bare_slash_root_path_is_empty(self):
        """Test that serving at the root is the empty prefix, not a slash."""
        self.assertEqual(load_config({ROOT_PATH_VAR: "/"}).root_path, "")

    def test_the_data_directory_is_taken_as_given(self):
        """Test that the bind mount can be pointed anywhere."""
        config = load_config({DATA_DIR_VAR: "/mnt/user/appdata/pairwise-ranking"})

        self.assertEqual(config.data_dir, Path("/mnt/user/appdata/pairwise-ranking"))

    def test_an_unusable_port_is_refused(self):
        """Test that a container does not quietly listen somewhere else."""
        for raw in ("eight thousand", "0", "-1", "70000"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    load_config({PORT_VAR: raw})

    def test_an_unimplemented_auth_mode_is_refused(self):
        """Test that a misspelt mode is not read as no authentication."""
        with self.assertRaises(ValueError):
            load_config({AUTH_MODE_VAR: "proxy"})

    def test_every_log_level_is_one_uvicorn_will_accept(self):
        """
        Test that no configured level can crash the server as it starts.

        web_main hands the level straight to uvicorn, which looks it up in a
        dict: a name this module forgave but uvicorn has not heard of - WARN,
        say, which the standard library answers to - was a KeyError out of
        uvicorn's startup instead of a readable message.
        """
        for raw in ("DEBUG", "info", " warning ", "WARN", "FATAL", "TRACE", "", "loud"):
            with self.subTest(raw=raw):
                level = load_config({LOG_LEVEL_VAR: raw}).log_level

                self.assertIn(level.lower(), UVICORN_LOG_LEVELS)
                self.assertIn(level.lower(), LOG_LEVELS)

    def test_a_standard_library_synonym_keeps_its_meaning(self):
        """Test that WARN is read as WARNING rather than thrown away."""
        self.assertEqual(load_config({LOG_LEVEL_VAR: "warn"}).log_level, "WARNING")
        self.assertEqual(load_config({LOG_LEVEL_VAR: "fatal"}).log_level, "CRITICAL")

    def test_an_unrecognized_log_level_falls_back_with_a_warning(self):
        """Test that a typo costs a warning rather than the whole log."""
        # A key is configured so the only warning in the log is the one under
        # test, rather than the generated-key warning as well.
        env = {LOG_LEVEL_VAR: "chatty", SECRET_KEY_VAR: "a-real-key"}
        with self.assertLogs("src.web.config", "WARNING") as logged:
            config = load_config(env)

        self.assertEqual(config.log_level, DEFAULT_LOG_LEVEL)
        self.assertIn(LOG_LEVEL_VAR, logged.output[0])

    def test_the_settled_level_means_the_same_to_the_standard_library(self):
        """
        Test that the name uvicorn is given is also the level logging applies.

        configure_logging resolves the name with getattr, so this is the other
        half of the agreement: WARN must arrive as WARNING rather than as the
        INFO fallback. TRACE is uvicorn's own level and has no standard-library
        equivalent, so it logs everything INFO and above - which is more than
        was asked for, never less.
        """
        for raw, expected in (
            ("warn", logging.WARNING),
            ("error", logging.ERROR),
            ("trace", logging.INFO),
        ):
            with self.subTest(raw=raw):
                level = load_config({LOG_LEVEL_VAR: raw}).log_level

                self.assertEqual(getattr(logging, level, logging.INFO), expected)


if __name__ == "__main__":
    unittest.main()
