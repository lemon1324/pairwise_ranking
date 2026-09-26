"""Route tests for the drawing register: the sheet the application opens on.

The register is the one screen with no project behind it, so these tests are
about files rather than about a session: what a directory of ``.pairrank``
files is drawn as, and what the five actions do to that directory. Every one of
them therefore asserts against the data directory or against the address the
route answered with - the file that appeared, the bytes that did not change,
the 303 and its query - rather than against a sentence on the page. A screen's
words are the capture pass's business; a route's behaviour is this file's.

Three shapes of route are covered, matching :mod:`src.web.routes.projects`:
the page, whose query describes its state completely; the callout fragments,
which are the popover and nothing around it; and the mutations, which are plain
posts answered with a redirect so that no outcome is a state only a form post
can reach.
"""

import csv
import json
import logging
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from src.data.format_version import CURRENT_FORMAT_VERSION
from src.data.legacy_storage import LegacyCsvStorage
from src.data.project_storage import ProjectStorage
from src.web.app import DAMAGED_STATUS, NEWER_FORMAT_STATUS, create_app
from src.web.config import WebConfig
from src.web.routes.projects import (
    DONE_NOTES,
    GHOST_ROW_ID,
    IMPORT_ERRORS,
    MAX_IMPORT_BYTES,
    NO_FIGURE,
    STANDING_NOTE,
)
from src.web.urls import DEFAULT_SHEET


# A format version this application has never heard of, for the newer-format
# tag and the page that goes with it.
FUTURE_VERSION = CURRENT_FORMAT_VERSION + 1


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

    Most of this file exercises failures the application is right to warn
    about - a refused project id, an import that is not a project, a damaged
    file - and an untouched root logger prints every one of them. Silencing is
    per logger and undone afterwards, and ``assertLogs`` still sees the
    records, so no test that cares about a warning is affected.

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


def project_data(
    name="Tasting", version=CURRENT_FORMAT_VERSION, items=2, votes=1
) -> dict:
    """
    Build a project dictionary in a given format version.

    Args:
        name: The project name to store.
        version: The format version to stamp.
        items: How many item entries to build.
        votes: How many vote entries to build, all between the first two items.

    Returns:
        dict: The project data, ready to be written as JSON.
    """
    return {
        "format_version": version,
        "name": name,
        "created": "2024-01-01T12:00:00",
        "modified": "2024-02-01T12:00:00",
        "items": [
            {
                "id": f"item-{n}",
                "name": f"Item {n}",
                "description": "",
                "identifier": str(n),
                "category": "General",
            }
            for n in range(1, items + 1)
        ],
        "votes": [
            {
                "id": f"vote-{n}",
                "winner_id": "item-1",
                "loser_id": "item-2",
                "weight": 2.0,
                "timestamp": "2024-01-10T10:00:00",
            }
            for n in range(1, votes + 1)
        ],
        "settings": {},
    }


def row_of(body: str, project_id: str) -> str:
    """
    Cut one row out of a rendered register.

    Args:
        body: The rendered page.
        project_id: The row's ``data-id``, which is the project's file name.

    Returns:
        str: The whole ``<tr>`` element, or an empty string when the register
        drew no row for that id.
    """
    match = re.search(
        rf'<tr class="bom-row[^>]*data-id="{re.escape(project_id)}"[^>]*>.*?</tr>',
        body,
        re.S,
    )
    return match.group(0) if match else ""


def note_of(body: str) -> str:
    """
    Read the sentence in the title block's Note cell.

    Args:
        body: The rendered page.

    Returns:
        str: The note, whitespace collapsed, or an empty string when the sheet
        drew no Note cell at all.
    """
    match = re.search(
        r'<span class="label">Note</span>\s*<p class="tb-text">(.*?)</p>',
        body,
        re.S,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


class RegisterTestCase(unittest.TestCase):
    """Base case giving each test an application over a temporary directory."""

    root_path = ""

    def setUp(self):
        """Build an application over a data directory :meth:`seed` filled."""
        silence(
            self, "src.web.registry", "src.web.app", "src.web.routes.projects"
        )
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        self.seed()
        self.app = create_app(config_for(self.data_dir, self.root_path))
        self.client = TestClient(self.app, root_path=self.root_path)

    def tearDown(self):
        """Remove the data directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def seed(self):
        """
        Fill the data directory before the application is built.

        A hook rather than something each test does afterwards, because
        :func:`~src.web.app.create_app` walks the directory as it starts - the
        legacy CSV migration runs there - so what is in it at that moment is
        part of the fixture.
        """

    def write_project(self, file_name: str, **kwargs) -> Path:
        """
        Write a project file from :func:`project_data`.

        Args:
            file_name: The name to write it under.
            **kwargs: Passed to :func:`project_data`.

        Returns:
            Path: The file written.
        """
        return self.write_raw(file_name, project_data(**kwargs))

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
            data if isinstance(data, str) else json.dumps(data, indent=2),
            encoding="utf-8",
        )
        return path

    def listed(self) -> set:
        """
        List the project files in the data directory.

        Returns:
            set: Every ``.pairrank`` file name that is there now.
        """
        return {path.name for path in self.data_dir.glob("*.pairrank")}

    def snapshot(self) -> dict:
        """
        Read every file in the data directory.

        Returns:
            dict: File name to bytes, for asserting that a refused action left
            the directory exactly as it found it.
        """
        return {
            path.name: path.read_bytes()
            for path in self.data_dir.iterdir()
            if path.is_file()
        }

    def redirect_of(self, response) -> tuple:
        """
        Take apart the redirect a mutation answered with.

        Args:
            response: The response, which must be a 303.

        Returns:
            tuple: Its path, and its query as a mapping of single values.
        """
        self.assertEqual(response.status_code, 303)
        parsed = urlparse(response.headers["location"])
        query = {key: value[0] for key, value in parse_qs(parsed.query).items()}
        return parsed.path, query

    def post(self, path: str, **kwargs):
        """
        Post without following the redirect that comes back.

        Args:
            path: The path to post to.
            **kwargs: Passed to the client.

        Returns:
            Response: The response, redirect and all.
        """
        return self.client.post(path, follow_redirects=False, **kwargs)


class TestRegisterListing(RegisterTestCase):
    """
    Test cases for the listing and the four conditions a file can be in.

    The conditions are the register's whole reason for existing: it is looked
    at before anything is opened, so a file it cannot open has to say so on its
    row rather than at the moment someone tries.
    """

    def seed(self):
        """Put one file of each condition in the directory."""
        self.write_project("Alpha.pairrank", name="Alpha", items=3, votes=2)
        self.write_project("Beta.pairrank", name="Beta", version=1)
        self.write_project("Future.pairrank", name="Future", version=FUTURE_VERSION)
        self.write_raw("Broken.pairrank", "{ not json at all")

    def setUp(self):
        """Fetch the register once; most tests here read the same page."""
        super().setUp()
        self.response = self.client.get("/")
        self.body = self.response.text

    def test_every_project_file_gets_a_row(self):
        """Test that the listing is the directory, whatever state it is in."""
        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(
            set(re.findall(r'data-id="([^"]+\.pairrank)"', self.body)),
            {"Alpha.pairrank", "Beta.pairrank", "Broken.pairrank", "Future.pairrank"},
        )

    def test_the_rows_are_one_long_table_in_file_name_order(self):
        """
        Test that the server folds nothing and orders by file name.

        The folding engine reads one table and moves its rows into columns
        without sorting them, so document order is the order they fold in - and
        is what a reader with no JavaScript gets.
        """
        self.assertEqual(self.body.count('<table class="bom"'), 1)
        self.assertNotIn("bom-col", self.body)
        self.assertNotIn("bom-page", self.body)
        self.assertEqual(
            re.findall(r'data-id="([^"]+\.pairrank)"', self.body),
            ["Alpha.pairrank", "Beta.pairrank", "Broken.pairrank", "Future.pairrank"],
        )

    def test_a_row_asks_for_its_own_callout_into_the_one_host(self):
        """
        Test that the row carries the hookup, targeted outside the sheet.

        `sheet:select` is what the engine fires on the row it has just
        selected; htmx hears it there. Any other target would put the callout
        inside the region the rows are swapped in, which is the one thing
        base.html keeps it out of.
        """
        row = row_of(self.body, "Alpha.pairrank")

        self.assertIn('hx-get="/projects/Alpha.pairrank/callout"', row)
        self.assertIn('hx-target="#row-callout"', row)
        self.assertIn('hx-trigger="sheet:select"', row)
        self.assertIn('aria-controls="row-callout"', row)
        # The register is a grid, so the row's aria-selected is announced.
        self.assertRegex(self.body, r'<table class="bom" role="grid" aria-label="Projects">')

    def test_a_current_file_is_untagged_and_carries_its_figures(self):
        """Test that a file in the current format is drawn as ordinary."""
        row = row_of(self.body, "Alpha.pairrank")

        self.assertNotIn('class="tag"', row)
        self.assertNotIn("is-retired", row)
        self.assertIn(">3</td>", row)
        self.assertIn(">2</td>", row)

    def test_an_old_format_file_is_tagged_and_left_openable(self):
        """
        Test that an old file is flagged and not dimmed.

        An old-format project is a perfectly good project: opening it upgrades
        it and keeps a backup. Drawing it like a file that cannot be opened
        would be a lie about the one condition that recovers itself.
        """
        row = row_of(self.body, "Beta.pairrank")

        self.assertIn('<span class="tag">Old format</span>', row)
        self.assertNotIn("is-retired", row)
        self.assertIn(">2</td>", row)

    def test_a_newer_format_file_is_tagged_dimmed_and_uncounted(self):
        """
        Test that a file from a newer version admits it cannot be counted.

        A newer format may have moved its keys, so a figure read out of it
        would be a guess. The row says so rather than printing a zero.
        """
        row = row_of(self.body, "Future.pairrank")

        self.assertIn('<span class="tag">Newer format</span>', row)
        self.assertIn("is-retired", row)
        self.assertEqual(row.count(NO_FIGURE), 2)

    def test_an_unreadable_file_is_tagged_dimmed_and_uncounted(self):
        """Test that a file that will not parse still gets a row."""
        row = row_of(self.body, "Broken.pairrank")

        self.assertIn('<span class="tag">Unreadable</span>', row)
        self.assertIn("is-retired", row)
        self.assertEqual(row.count(NO_FIGURE), 2)

    def test_the_title_block_counts_the_files_and_the_problems(self):
        """Test that the sheet says how many files there are and how many are bad."""
        self.assertRegex(self.body, r'<span class="num">4</span>\s*files')
        self.assertRegex(
            self.body, r'&middot;\s*<span class="num">2</span>\s*can&rsquo;t be opened'
        )

    def test_drawing_the_register_changes_nothing_in_the_directory(self):
        """
        Test that listing never migrates a file or leaves a backup.

        ProjectStorage.load upgrades an old file in place; the register probes
        instead, precisely so that opening the picker does not silently rewrite
        every old project in the directory.
        """
        before = self.snapshot()

        self.client.get("/")

        self.assertEqual(self.snapshot(), before)

    def test_a_differently_cased_extension_is_not_listed(self):
        """
        Test that the listing and the addressing agree about what a project is.

        ProjectStorage refuses a differently-cased extension, so a row for
        SHOUT.PAIRRANK would be one the register could draw and nothing in the
        product could act on.
        """
        self.write_project("Shout.PAIRRANK", name="Shout")

        body = self.client.get("/").text

        self.assertEqual(row_of(body, "Shout.PAIRRANK"), "")

    def test_the_sheet_asks_for_the_folding_engine(self):
        """Test that the script is on the page, and deferred."""
        self.assertRegex(self.body, r'<script src="[^"]*js/sheet\.js" defer></script>')

    def test_the_sheet_has_one_heading_and_it_is_the_title_block_s(self):
        """
        Test that the app name in the bar is not a second <h1>.

        Every other screen hides the bar's title on desktop and shows it on
        phones, where the title block's TITLE cell is hidden, so exactly one of
        the two is ever a heading. The register shows both at once - there is
        no project, so `is-app` keeps the application's name up at every width
        - and two <h1>s on one screen is two documents. The sheet's name stays
        the heading; the bar carries a brand mark.
        """
        headings = re.findall(r"<h1[^>]*>(.*?)</h1>", self.body, re.S)

        self.assertEqual(headings, ["Drawing register"])
        self.assertIn(
            '<p class="sheet-title-text">Pairwise Ranking</p>', self.body
        )

    def test_the_boot_script_binds_its_listener_on_the_window(self):
        """
        Test that the row this page arrives on is selected from `window`.

        Not a style preference, and the four screens that have not been built
        will copy whichever way this is written. htmx wires every hx-trigger
        from a listener it binds on **document**, registered when its own
        deferred script runs - before this inline script has even been parsed.
        DOMContentLoaded is fired at the document and bubbles, so a listener on
        `window` runs in the bubble phase, strictly after every document one.
        Bind this on `document` and it becomes a race this side can lose:
        sheet:select fires before the row has an hx-trigger to hear it, htmx
        never asks for the callout, and the sheet comes up with the form
        missing - silently, on every page load.
        """
        body = self.client.get("/?form=new").text
        boot = [
            block
            for block in re.findall(r"<script>(.*?)</script>", body, re.S)
            if "window.sheet.select" in block
        ]

        self.assertEqual(len(boot), 1)
        self.assertIn('window.addEventListener("DOMContentLoaded"', boot[0])
        self.assertNotIn("document.addEventListener", boot[0])

    def test_the_pager_is_drawn_but_offers_nothing_yet(self):
        """
        Test that the sheet count starts at one of one, both buttons dead.

        The server cannot know how many sheets the rows fold onto - that is a
        measurement of the reader's window - so it states the only thing it
        knows and the engine corrects it. With no engine that statement stays
        true: one long sheet, and nowhere to page to.
        """
        self.assertIn('<span class="num" id="sheet-no">1 of 1</span>', self.body)
        for button in ("page-prev", "page-next"):
            with self.subTest(button=button):
                markup = re.search(rf'<button[^>]*id="{button}"[^>]*>', self.body)
                self.assertIsNotNone(markup)
                self.assertIn("disabled", markup.group(0))


class TestEmptyRegister(RegisterTestCase):
    """Test cases for a data directory with no projects in it."""

    def test_an_empty_directory_draws_the_empty_state(self):
        """Test that nothing to list is a statement rather than a blank table."""
        body = self.client.get("/").text

        self.assertNotIn('class="bom-row', body)
        self.assertIn('class="bom-empty"', body)
        self.assertIn(self.data_dir.name, body)

    def test_the_empty_state_offers_both_ways_to_get_a_project(self):
        """Test that the dead end offers the two actions that end it."""
        body = self.client.get("/").text
        empty = re.search(r'<div class="bom-empty">.*?</div>\s*</div>', body, re.S)

        self.assertIsNotNone(empty)
        self.assertIn('href="/?form=new"', empty.group(0))
        self.assertIn('href="/?form=import"', empty.group(0))

    def test_the_empty_state_names_the_two_shortcuts(self):
        """
        Test that the empty state draws N and I on its buttons.

        The keys work whether or not there are rows - they are declared on the
        title block's cells, and sheet.js presses them from the document. An
        empty directory is exactly where someone has not yet learned them, so
        the legends are on the buttons here as they are in the mockup.
        """
        body = self.client.get("/").text
        empty = re.search(r'<div class="bom-empty">.*?</div>\s*</div>', body, re.S)

        self.assertIsNotNone(empty)
        self.assertIn('New project <span class="key">N</span>', empty.group(0))
        self.assertIn('Import <span class="key">I</span>', empty.group(0))

    def test_a_directory_that_does_not_exist_is_still_the_empty_state(self):
        """
        Test that a missing bind mount draws the empty sheet, not an error.

        The container is started with the share unmounted more often than
        anyone would like, and an empty register says more about it than a 500.
        """
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="bom-empty"', response.text)

    def test_a_mistyped_form_draws_the_register_rather_than_an_error(self):
        """Test that an address nobody wrote is answered with the sheet."""
        response = self.client.get("/?form=destroy")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f'data-id="{GHOST_ROW_ID}"', response.text)


class TestRegisterNote(RegisterTestCase):
    """
    Test cases for the Note cell, the one place the register reports itself.

    Every mutation redirects with ``done=`` and ``selected=`` on the query, and
    this cell is the only thing on the sheet that reads them: it is how someone
    who has just pressed Create learns that a file appeared and what it was
    called. The rest of the suite asserts the redirect and stops there, so
    until these were written the whole of ``_note`` could have rendered nothing
    and every other test would still have passed - the same shape of mistake as
    the `row.items` bug, which also rendered silently and wrongly.

    The file name in a note comes from the register's own scan and never from
    the query, so a browser cannot put words on the sheet; the two fallback
    cases below are what enforce that.
    """

    def seed(self):
        """Put one project on the register to act on."""
        self.write_project("Alpha.pairrank", name="Alpha", items=3, votes=2)

    def standing(self) -> str:
        """
        Build the note the register carries when nothing has just happened.

        Returns:
            str: The sentence, as the template would have rendered it.
        """
        return STANDING_NOTE.format(directory=self.data_dir)

    def note(self, query: str = "") -> str:
        """
        Fetch the register and read its Note cell.

        Args:
            query: A query string to fetch it with, "?done=..." and all.

        Returns:
            str: The note.
        """
        return note_of(self.client.get(f"/{query}").text)

    def test_the_standing_note_says_what_the_register_lists(self):
        """Test that the resting state names the directory and the way in."""
        self.assertEqual(self.note(), self.standing())
        self.assertIn(str(self.data_dir), self.note())

    def test_creating_says_so_on_the_sheet_it_returns_to(self):
        """Test that the redirect's done= reaches the cell as a sentence."""
        response = self.client.post(
            "/projects/new", data={"name": "Keyswitches"}, follow_redirects=True
        )

        self.assertEqual(note_of(response.text), "Created Keyswitches.pairrank.")

    def test_duplicating_says_what_it_did_not_copy(self):
        """Test that the copy's note names the file and the votes it dropped."""
        response = self.client.post(
            "/projects/Alpha.pairrank/duplicate",
            data={"name": "Alpha copy"},
            follow_redirects=True,
        )

        self.assertEqual(
            note_of(response.text), "Duplicated Alpha copy.pairrank, without votes."
        )

    def test_importing_says_the_name_the_file_actually_landed_under(self):
        """
        Test that the note reports the written name, not the uploaded one.

        An import of a name already on the register is suffixed rather than
        overwritten, so the sentence has to come from the file that appeared.
        """
        raw = json.dumps(project_data(name="Alpha", items=1, votes=0)).encode()

        response = self.client.post(
            "/projects/import",
            files={"file": ("Alpha.pairrank", raw, "application/json")},
            follow_redirects=True,
        )

        self.assertEqual(note_of(response.text), "Imported Alpha (2).pairrank.")

    def test_every_mutation_has_a_sentence_of_its_own(self):
        """Test that no two mutations report themselves the same way."""
        notes = {
            done: note_of(
                self.client.get(f"/?done={done}&selected=Alpha.pairrank").text
            )
            for done in DONE_NOTES
        }

        self.assertEqual(len(set(notes.values())), len(DONE_NOTES))
        for done, sentence in notes.items():
            with self.subTest(done=done):
                self.assertIn("Alpha.pairrank", sentence)
                self.assertNotEqual(sentence, self.standing())

    def test_a_done_for_a_file_that_is_not_listed_falls_back(self):
        """
        Test that a note is only drawn about a file the register can see.

        The name is taken from the row, so a query naming a file that is not
        there has nothing to name and the standing note is the honest answer.
        """
        self.assertEqual(
            self.note("?done=created&selected=Ghost.pairrank"), self.standing()
        )

    def test_a_done_nothing_writes_falls_back(self):
        """Test that an invented code draws the standing note, not an error."""
        self.assertEqual(
            self.note("?done=deleted&selected=Alpha.pairrank"), self.standing()
        )

    def test_the_note_never_repeats_what_the_query_said(self):
        """
        Test that nothing a browser sends is echoed into the cell.

        `selected` is a file name from the query and the note is a sentence on
        the sheet; the only thing joining them is a lookup in the register's
        own scan, which is what keeps the second from being written by the
        first.
        """
        note = self.note("?done=created&selected=%3Cb%3Eoops%3C%2Fb%3E")

        self.assertEqual(note, self.standing())
        self.assertNotIn("oops", note)


class TestRowCallout(RegisterTestCase):
    """
    Test cases for the fragment one row's actions arrive in.

    What a condition costs a file is decided here: a file this application
    cannot read loses Open and Duplicate and keeps Download, because taking a
    copy away is the one thing that still makes sense to do with it.
    """

    def seed(self):
        """Put one file of each condition in the directory."""
        self.write_project("Alpha.pairrank", name="Alpha")
        self.write_project("Beta.pairrank", name="Beta", version=1)
        self.write_project("Future.pairrank", name="Future", version=FUTURE_VERSION)
        self.write_raw("Broken.pairrank", "{ not json at all")

    def callout(self, project_id: str) -> str:
        """
        Fetch one row's callout.

        Args:
            project_id: The project's file name.

        Returns:
            str: The fragment.
        """
        return self.client.get(f"/projects/{project_id}/callout").text

    def test_a_callout_is_the_popover_and_nothing_around_it(self):
        """
        Test that the fragment is swappable into a host that already exists.

        It lands in `#row-callout`, so a shell, a wrapper or a second host
        would be swapped in with it. Actions inside it may still *target* the
        host, which is how a callout replaces itself with a form.
        """
        body = self.callout("Alpha.pairrank")

        self.assertNotIn("<html", body)
        self.assertNotIn('id="row-callout"', body)
        self.assertEqual(body.count("bom-callout"), 1)
        self.assertTrue(body.strip().startswith('<div class="bom-callout'))

    def test_a_current_file_offers_open_duplicate_and_download(self):
        """Test that a good file offers all three actions, at their addresses."""
        body = self.callout("Alpha.pairrank")

        self.assertIn('href="/projects/Alpha.pairrank/open"', body)
        self.assertIn('hx-get="/projects/Alpha.pairrank/duplicate"', body)
        self.assertIn('href="/projects/Alpha.pairrank/download"', body)

    def test_open_declares_the_key_the_engine_presses(self):
        """
        Test that the Enter legend is wired rather than only drawn.

        sheet.js presses whatever carries `data-sheet-key`, and ARIA is told
        the key value rather than the glyph on the cell.
        """
        body = self.callout("Alpha.pairrank")
        action = re.search(r'<a class="strip-action"[^>]*data-action="open"[^>]*>', body)

        self.assertIsNotNone(action)
        self.assertIn('data-sheet-key="Enter"', action.group(0))
        self.assertIn('aria-keyshortcuts="Enter"', action.group(0))

    def test_an_old_format_file_keeps_every_action_and_says_what_opening_does(self):
        """
        Test that the upgrade is stated before it happens, not after.

        And that the file it leaves behind is named. Migration writes the
        original to the project's own name with the version in the suffix, so
        the name is derivable from the row and there is no reason to say "a
        backup" and leave someone hunting for it. The desktop path's shared
        `reason` still says "a backup", which is all it can say.
        """
        body = self.callout("Beta.pairrank")

        self.assertIn('href="/projects/Beta.pairrank/open"', body)
        self.assertIn('hx-get="/projects/Beta.pairrank/duplicate"', body)
        self.assertIn(f"version {CURRENT_FORMAT_VERSION}", body)
        self.assertIn("Beta.pairrank.v1.bak", body)

    def test_the_backup_the_callout_names_is_the_one_opening_writes(self):
        """
        Test that the two sentences about the same file agree.

        The callout derives the backup's name from the row; the migration
        writes it from the path. Nothing but this test holds the two together,
        and a callout naming a file that never appears is worse than one that
        says "a backup".
        """
        named = re.search(r"(\S+\.pairrank\.v\d+\.bak)", self.callout("Beta.pairrank"))
        self.assertIsNotNone(named)

        self.client.get("/projects/Beta.pairrank/open", follow_redirects=False)

        self.assertIn(named.group(1), {p.name for p in self.data_dir.iterdir()})

    def test_a_newer_format_file_offers_only_download(self):
        """Test that nothing is offered that this application cannot do."""
        body = self.callout("Future.pairrank")

        self.assertNotIn("/open", body)
        self.assertNotIn("/duplicate", body)
        self.assertIn('href="/projects/Future.pairrank/download"', body)
        self.assertIn("strip-confirm", body)

    def test_an_unreadable_file_offers_only_download_and_says_why(self):
        """Test that the cause is on the callout, in words."""
        body = self.callout("Broken.pairrank")

        self.assertNotIn("/open", body)
        self.assertNotIn("/duplicate", body)
        self.assertIn('href="/projects/Broken.pairrank/download"', body)
        self.assertIn("not valid JSON", body)

    def test_a_project_that_is_not_there_is_not_found(self):
        """Test that a row that has gone since the page was drawn 404s."""
        response = self.client.get("/projects/Missing.pairrank/callout")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Not found", response.text)

    def test_an_id_reaching_out_of_the_directory_is_refused(self):
        """
        Test that a name a browser invented cannot address another directory.

        Refused and not-there are the same answer on purpose: a browser asking
        about a file it has no business naming learns nothing it did not
        already know. Some of these never reach the route at all - a %2F is a
        separator by the time the router sees it - which is the same answer by
        a shorter road.
        """
        for project_id in (
            "..%2Fsecrets.pairrank",
            "sub%5Cother.pairrank",
            "C%3A%5Csecrets.pairrank",
            "notes.txt",
            "Alpha.PAIRRANK",
            "%20",
        ):
            with self.subTest(project_id=project_id):
                response = self.client.get(f"/projects/{project_id}/callout")

                self.assertEqual(response.status_code, 404)
                self.assertIn("Not found", response.text)

    def test_a_refused_id_is_logged(self):
        """
        Test that the refusal leaves a record.

        It is the one thing here worth going looking for afterwards, and the
        page deliberately says nothing about why.
        """
        with self.assertLogs("src.web.routes.projects", "WARNING") as logged:
            self.client.get("/projects/notes.txt/callout")

        self.assertIn("notes.txt", logged.output[0])


class TestNewProject(RegisterTestCase):
    """Test cases for starting a project from the register."""

    def seed(self):
        """Put one project in the way of the names tried here."""
        self.write_project("Alpha.pairrank", name="Alpha")

    def test_the_new_form_hangs_off_a_ghost_row(self):
        """
        Test that New draws a row for the engine to place its callout against.

        The folding engine positions a callout beside a row's find-number cell
        and keeps the host hidden when there is no row, so an action with no
        project of its own needs one invented for it.
        """
        body = self.client.get("/?form=new").text

        self.assertIn(f'data-id="{GHOST_ROW_ID}"', body)
        self.assertIn('hx-get="/projects/new/callout"', body)
        self.assertIn(f"window.sheet.select({json.dumps(GHOST_ROW_ID)})", body)

    def test_the_new_form_posts_rather_than_swaps(self):
        """
        Test that the form is a plain post to the create route.

        Deliberate: every answer this form can get is a page of the register
        with an address, which is what makes a refusal survive a reload and
        work with the engine switched off.
        """
        body = self.client.get("/projects/new/callout").text

        self.assertIn('method="post"', body)
        self.assertIn('action="/projects/new"', body)
        self.assertNotIn("hx-post", body)

    def test_a_name_taken_after_the_check_is_still_not_written_over(self):
        """
        Test that the collision check inside the lock is the one that counts.

        The check that answers the form runs before the lock is taken, and
        `ProjectStorage.create_new` writes through whatever is at the path, so
        a file that appears in between would be destroyed by a create that had
        already been told the name was free. The other two mutations each
        choose their free name inside the lock; this one is held to the same
        thing. Driven by disabling the outer check, which is the only way to
        stand in the window it leaves.
        """
        original = self.snapshot()

        with patch(
            "src.web.routes.projects._draft",
            return_value=("Alpha.pairrank", None),
        ):
            response = self.post("/projects/new", data={"name": "Alpha"})

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/")
        self.assertEqual(query, {"form": "new", "name": "Alpha", "submitted": "1"})
        self.assertEqual(self.snapshot(), original)

    def test_the_form_declares_both_of_the_keys_it_draws(self):
        """
        Test that Save takes Enter as surely as Cancel takes Esc.

        Enter submitted this form by itself only while the caret was in the
        name field - the browser's implicit submission - and the engine leaves
        clicks inside `#row-callout` alone on purpose, so clicking anywhere in
        the popover that is not the input took the caret out and left the ↵ on
        the button drawing a key nothing pressed. Nothing in sheet.js makes
        Enter mean Save; it has to be declared, the way Escape is.
        """
        for url in (
            "/projects/new/callout",
            "/projects/Alpha.pairrank/duplicate",
        ):
            with self.subTest(url=url):
                body = self.client.get(url).text
                save = re.search(r"<button[^>]*is-primary[^>]*>", body, re.S)
                cancel = re.search(r"<a[^>]*data-sheet-key=\"Escape\"[^>]*>", body)

                self.assertIsNotNone(save)
                self.assertIn('data-sheet-key="Enter"', save.group(0))
                self.assertIn('aria-keyshortcuts="Enter"', save.group(0))
                self.assertIsNotNone(cancel)

    def test_creating_writes_the_file_and_comes_back_to_it(self):
        """Test that a new project is on disk and selected when the page returns."""
        response = self.post("/projects/new", data={"name": "Keyswitches"})

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/")
        self.assertEqual(query, {"selected": "Keyswitches.pairrank", "done": "created"})
        self.assertIn("Keyswitches.pairrank", self.listed())

    def test_the_created_project_carries_the_name_that_was_typed(self):
        """Test that the file name is derived from the name, not the other way."""
        self.post("/projects/new", data={"name": "  Keyswitches  "})

        project = ProjectStorage.load(self.data_dir / "Keyswitches.pairrank")

        self.assertEqual(project.name, "Keyswitches")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])

    def test_a_name_that_is_not_a_file_name_is_made_into_one(self):
        """
        Test that a name with separators in it cannot address a path.

        The project keeps the name the user typed; only the file it is saved
        as is sanitized.
        """
        self.post("/projects/new", data={"name": "Cost/Benefit"})

        self.assertIn("Cost_Benefit.pairrank", self.listed())
        self.assertEqual(
            ProjectStorage.load(self.data_dir / "Cost_Benefit.pairrank").name,
            "Cost/Benefit",
        )

    def test_a_name_whose_file_is_taken_is_refused_without_touching_it(self):
        """
        Test that creating never overwrites, and says so instead.

        A collision is answered by reopening the form on the draft rather than
        by quietly saving "Alpha (2)" under a name nobody asked for.
        """
        before = self.snapshot()

        response = self.post("/projects/new", data={"name": "Alpha"})

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/")
        self.assertEqual(query, {"form": "new", "name": "Alpha", "submitted": "1"})
        self.assertEqual(self.snapshot(), before)

    def test_a_collision_is_compared_without_regard_to_case(self):
        """
        Test that a name differing only in case is still a collision.

        The filesystems this runs on are case-insensitive, so "alpha" and
        "Alpha" are one file on the share whatever this answered.
        """
        before = self.snapshot()

        response = self.post("/projects/new", data={"name": "alpha"})

        _, query = self.redirect_of(response)
        self.assertEqual(query.get("form"), "new")
        self.assertEqual(self.snapshot(), before)

    def test_an_empty_name_is_refused(self):
        """Test that pressing Create on an empty field writes nothing."""
        before = self.snapshot()

        response = self.post("/projects/new", data={"name": "   "})

        _, query = self.redirect_of(response)
        self.assertEqual(query, {"form": "new", "submitted": "1"})
        self.assertEqual(self.snapshot(), before)

    def test_the_reopened_form_says_what_stopped_the_write(self):
        """
        Test that the refusal the user reads is the one that refused them.

        The same check runs when the form is drawn and when it is posted, so
        the redirect carrying the draft back is enough to reproduce the error.
        """
        body = self.client.get("/projects/new/callout?name=Alpha&submitted=1").text

        self.assertIn("is-error", body)
        # The whole path, because this line replaces the hint that said where
        # the project would have been saved.
        self.assertIn(f"{self.data_dir}/Alpha.pairrank already exists", body)

    def test_an_empty_field_is_not_an_error_until_it_has_been_submitted(self):
        """Test that opening the form does not open it complaining."""
        body = self.client.get("/projects/new/callout").text

        self.assertNotIn("is-error", body)
        self.assertIn("Saves as", body)

    def test_a_mistyped_submitted_draws_a_fresh_form(self):
        """
        Test that `submitted` other than 1 is no submission, not a 422.

        On the register, and on both forms' fragments.
        """
        # Empty and free names, which are errors only once submitted.
        for url in ("/?form=new&submitted=yes",
                    "/?form=duplicate&project=Alpha.pairrank&submitted=on",
                    "/projects/new/callout?name=&submitted=yes",
                    "/projects/new/callout?submitted=2",
                    "/projects/Alpha.pairrank/duplicate?name=Fresh&submitted=on"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
                self.assertNotIn("is-error", response.text)
                self.assertNotIn("submitted=", response.text)


class TestDuplicateProject(RegisterTestCase):
    """Test cases for copying a project without its votes."""

    def seed(self):
        """Put a project with votes, and something to collide with, in place."""
        self.write_project("Alpha.pairrank", name="Alpha", items=3, votes=4)
        self.write_project("Taken.pairrank", name="Taken")
        self.write_project("Future.pairrank", name="Future", version=FUTURE_VERSION)
        self.write_raw("Broken.pairrank", "{ not json at all")

    def test_the_duplicate_form_opens_on_a_default_name(self):
        """Test that the copy is proposed rather than demanded."""
        body = self.client.get("/projects/Alpha.pairrank/duplicate").text

        self.assertIn('value="Alpha copy"', body)
        self.assertIn('action="/projects/Alpha.pairrank/duplicate"', body)

    def test_the_duplicate_form_replaces_that_row_s_callout(self):
        """
        Test that the form opens on the row being copied, not on a ghost row.

        Duplicate belongs to a project, so its callout hangs where that
        project's actions were.
        """
        body = self.client.get("/?form=duplicate&project=Alpha.pairrank").text
        row = row_of(body, "Alpha.pairrank")

        self.assertNotIn(f'data-id="{GHOST_ROW_ID}"', body)
        self.assertIn('hx-get="/projects/Alpha.pairrank/duplicate"', row)
        self.assertIn('window.sheet.select("Alpha.pairrank")', body)

    def test_a_duplicate_form_for_a_project_that_is_gone_is_dropped(self):
        """Test that a stale address draws the register rather than a form."""
        body = self.client.get("/?form=duplicate&project=Missing.pairrank").text

        self.assertNotIn("/projects/Missing.pairrank/duplicate", body)
        self.assertNotIn(f'data-id="{GHOST_ROW_ID}"', body)

    def test_duplicating_keeps_the_items_and_drops_the_votes(self):
        """Test that the one thing the action promises is the thing it does."""
        response = self.post(
            "/projects/Alpha.pairrank/duplicate", data={"name": "Alpha again"}
        )

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/")
        self.assertEqual(
            query, {"selected": "Alpha again.pairrank", "done": "duplicated"}
        )
        copy = ProjectStorage.load(self.data_dir / "Alpha again.pairrank")
        self.assertEqual(copy.name, "Alpha again")
        self.assertEqual(len(copy.items), 3)
        self.assertEqual(copy.votes, [])

    def test_the_source_keeps_its_votes(self):
        """Test that a copy is a copy: the original is not emptied by it."""
        self.post("/projects/Alpha.pairrank/duplicate", data={"name": "Alpha again"})

        source = ProjectStorage.load(self.data_dir / "Alpha.pairrank")

        self.assertEqual(len(source.votes), 4)

    def test_a_name_whose_file_is_taken_is_refused_without_touching_it(self):
        """
        Test that duplicating collides the same way creating does.

        The two forms are one template and one check, and the check is the one
        place a suffixed name could sneak in unasked-for.
        """
        before = self.snapshot()

        response = self.post(
            "/projects/Alpha.pairrank/duplicate", data={"name": "Taken"}
        )

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/")
        self.assertEqual(
            query,
            {
                "form": "duplicate",
                "project": "Alpha.pairrank",
                "name": "Taken",
                "submitted": "1",
            },
        )
        self.assertEqual(self.snapshot(), before)

    def test_an_empty_name_is_refused(self):
        """Test that a copy cannot be made without being named."""
        before = self.snapshot()

        response = self.post("/projects/Alpha.pairrank/duplicate", data={"name": ""})

        _, query = self.redirect_of(response)
        self.assertEqual(query.get("form"), "duplicate")
        self.assertEqual(self.snapshot(), before)

    def test_duplicating_a_project_that_is_not_there_is_not_found(self):
        """Test that a stale row cannot be copied."""
        response = self.post(
            "/projects/Missing.pairrank/duplicate", data={"name": "Copy"}
        )

        self.assertEqual(response.status_code, 404)

    def test_duplicating_an_unreadable_file_lands_on_the_damaged_page(self):
        """
        Test that a copy of a file that will not read is a typed failure.

        The callout does not offer Duplicate on such a row, but the address
        exists and a browser can reach it.
        """
        response = self.post(
            "/projects/Broken.pairrank/duplicate", data={"name": "Copy"}
        )

        self.assertEqual(response.status_code, DAMAGED_STATUS)
        self.assertIn("damaged", response.text)
        self.assertNotIn("Copy.pairrank", self.listed())

    def test_duplicating_a_newer_format_file_says_so(self):
        """Test that the newer-format page is reached rather than the damaged one."""
        response = self.post(
            "/projects/Future.pairrank/duplicate", data={"name": "Copy"}
        )

        self.assertEqual(response.status_code, NEWER_FORMAT_STATUS)
        self.assertIn("newer version", response.text)
        self.assertNotIn("Copy.pairrank", self.listed())


class TestDownloadProject(RegisterTestCase):
    """Test cases for taking a copy of a project file away."""

    def seed(self):
        """Put a good file and an unreadable one in the directory."""
        self.source = self.write_project("Alpha.pairrank", name="Alpha")
        self.write_raw("Broken.pairrank", "{ not json at all")

    def test_a_download_is_the_file_exactly_as_it_is_on_disk(self):
        """Test that downloading neither migrates nor re-serializes."""
        response = self.client.get("/projects/Alpha.pairrank/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.source.read_bytes())
        self.assertIn("application/json", response.headers["content-type"])

    def test_a_download_is_named_and_offered_as_an_attachment(self):
        """Test that the file arrives under its own name, twice over."""
        response = self.client.get("/projects/Alpha.pairrank/download")
        disposition = response.headers["content-disposition"]

        self.assertIn("attachment", disposition)
        self.assertIn('filename="Alpha.pairrank"', disposition)
        self.assertIn("filename*=UTF-8''Alpha.pairrank", disposition)

    def test_an_unreadable_file_can_still_be_taken_away(self):
        """
        Test that the one action a damaged file keeps actually works.

        Download is left on the warning callout precisely so that a file this
        application cannot parse can be got out to something that can.
        """
        response = self.client.get("/projects/Broken.pairrank/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"{ not json at all")

    def test_downloading_a_project_that_is_not_there_is_not_found(self):
        """Test that a stale row does not serve an empty file."""
        response = self.client.get("/projects/Missing.pairrank/download")

        self.assertEqual(response.status_code, 404)

    def test_an_id_reaching_out_of_the_directory_is_refused(self):
        """Test that download is not a way to read an arbitrary path."""
        with self.assertLogs("src.web.registry", "WARNING"):
            response = self.client.get("/projects/notes.txt/download")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.get("/projects/..%2Fsecrets.pairrank/download").status_code, 404
        )


class TestImportProject(RegisterTestCase):
    """
    Test cases for taking a file in from the desktop app.

    An upload is the one thing here that arrives from outside the directory, so
    it is the one thing that has to be judged before it is written: what it is
    named, how big it is, and whether it is a project at all.
    """

    def seed(self):
        """Put a project in the way of an import of the same name."""
        self.write_project("Alpha.pairrank", name="Alpha", items=3, votes=2)

    def upload(self, file_name: str, raw: bytes) -> dict:
        """
        Build the multipart payload of one uploaded file.

        Args:
            file_name: The name the browser would send.
            raw: The file's bytes.

        Returns:
            dict: The ``files`` argument for a post.
        """
        return {"file": (file_name, raw, "application/json")}

    def good_bytes(self, name="Imported", items=4, votes=3) -> bytes:
        """
        Build the bytes of a project file that has not been written anywhere.

        Args:
            name: The project name.
            items: How many item entries.
            votes: How many vote entries.

        Returns:
            bytes: The file's contents.
        """
        return json.dumps(project_data(name=name, items=items, votes=votes)).encode()

    def test_the_import_form_hangs_off_a_ghost_row(self):
        """Test that Import, like New, gets a row invented for its callout."""
        body = self.client.get("/?form=import").text

        self.assertIn(f'data-id="{GHOST_ROW_ID}"', body)
        self.assertIn('hx-get="/projects/import/callout"', body)

    def test_the_import_callout_says_where_the_focus_goes(self):
        """
        Test that the drop zone is the callout's one [autofocus] field.

        sheet.js focuses `[autofocus]` after a callout swap, and a callout
        without one leaves the focus on whatever the last swap left it on.
        It cannot be the file input, which is visually hidden: Chrome matches
        :focus-visible on a programmatically focused field only when it
        carries `autofocus`, and the ring would be drawn on a one-pixel box in
        any case. So it is the label that is the whole dashed drop zone, made
        a keyboard target with tabindex.
        """
        body = self.client.get("/projects/import/callout").text
        focused = re.findall(r"<(\w+)[^>]*\bautofocus\b", body)

        self.assertEqual(focused, ["label"])
        self.assertIn('tabindex="0"', re.search(r"<label[^>]*>", body).group(0))

    def test_import_declares_the_key_its_legend_draws(self):
        """
        Test that the ↵ on the Import button is wired to the button.

        Nothing in the engine makes Enter mean Save: it presses whatever
        carries `data-sheet-key`, and this form has no text field for the
        browser's own implicit submission to work from either - its one input
        is the hidden file input. Undeclared, the legend drew a key nothing
        pressed and Enter fell through to a `sheet:open` no one listens for.
        """
        body = self.client.get("/projects/import/callout").text
        button = re.search(r"<button[^>]*is-primary[^>]*>", body, re.S)

        self.assertIsNotNone(button)
        self.assertIn('data-sheet-key="Enter"', button.group(0))
        self.assertIn('aria-keyshortcuts="Enter"', button.group(0))

    def test_a_preview_describes_the_file_without_writing_it(self):
        """
        Test that choosing a file says what is in it and changes nothing.

        Nothing is kept between the preview and the import: the file is
        parsed, described and dropped, which is why pressing Import uploads it
        again.
        """
        before = self.snapshot()

        response = self.post(
            "/projects/import/preview",
            files=self.upload("Imported.pairrank", self.good_bytes()),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Imported", response.text)
        self.assertIn(">4</span> items", response.text)
        self.assertIn(">3</span> votes", response.text)
        self.assertEqual(self.snapshot(), before)

    def test_a_preview_names_the_file_it_would_actually_be_saved_as(self):
        """Test that a collision is stated before the import, not after it."""
        response = self.post(
            "/projects/import/preview",
            files=self.upload("Alpha.pairrank", self.good_bytes(name="Alpha")),
        )

        self.assertIn("Alpha (2).pairrank", response.text)

    def test_a_preview_puts_the_chosen_name_on_the_drop_zone(self):
        """
        Test that the box a file was dropped on stops asking for one.

        The drop zone is a label around the file input, so it cannot be
        swapped with the detail area without throwing away the file the
        browser has already chosen. The name goes out of band instead, which
        changes the words and leaves the input alone.
        """
        response = self.post(
            "/projects/import/preview",
            files=self.upload("Imported.pairrank", self.good_bytes()),
        )

        self.assertIn('id="import-lead"', response.text)
        self.assertIn('hx-swap-oob="true"', response.text)
        self.assertIn("Imported.pairrank</span>", response.text)

    def test_a_preview_of_nothing_leaves_the_drop_zone_asking(self):
        """Test that an empty upload does not blank the invitation."""
        response = self.post(
            "/projects/import/preview", files={"file": ("", b"")}
        )

        self.assertNotIn("hx-swap-oob", response.text)

    def test_a_preview_of_something_that_is_not_a_project_says_so(self):
        """Test that the file is judged before Import is ever pressed."""
        response = self.post(
            "/projects/import/preview",
            files=self.upload("Notes.csv", b"id,name\n1,Item\n"),
        )

        self.assertIn(IMPORT_ERRORS["type"], response.text)

    def test_a_preview_of_an_unreadable_project_gives_the_reason(self):
        """Test that a .pairrank that will not parse is described, not tagged."""
        response = self.post(
            "/projects/import/preview",
            files=self.upload("Junk.pairrank", b"{ not json at all"),
        )

        self.assertIn("is not a project file", response.text)

    def test_importing_writes_the_bytes_exactly_as_they_arrived(self):
        """
        Test that an import is not an opening.

        The bytes go in untouched, so an old-format file stays an old-format
        file and is upgraded the first time it is actually opened - with the
        backup that goes with that.
        """
        raw = json.dumps(project_data(name="Ancient", version=1)).encode()

        response = self.post(
            "/projects/import", files=self.upload("Ancient.pairrank", raw)
        )

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/")
        self.assertEqual(query, {"selected": "Ancient.pairrank", "done": "imported"})
        self.assertEqual((self.data_dir / "Ancient.pairrank").read_bytes(), raw)
        self.assertIn(
            '<span class="tag">Old format</span>',
            row_of(self.client.get("/").text, "Ancient.pairrank"),
        )

    def test_importing_over_a_name_that_is_taken_suffixes_instead(self):
        """
        Test that an import can never destroy a project already listed.

        Unlike New and Duplicate, which refuse a taken name, an import is given
        a free one: the user is handing over a file, not choosing a name, and
        there is nothing to send them back to.
        """
        before = (self.data_dir / "Alpha.pairrank").read_bytes()

        response = self.post(
            "/projects/import",
            files=self.upload("Alpha.pairrank", self.good_bytes(name="Alpha")),
        )

        _, query = self.redirect_of(response)
        self.assertEqual(query["selected"], "Alpha (2).pairrank")
        self.assertEqual((self.data_dir / "Alpha.pairrank").read_bytes(), before)

    def test_a_file_that_is_not_a_pairrank_is_refused_by_its_name(self):
        """
        Test that the wrong kind of file is turned away before it is parsed.

        The name is judged here rather than by the importer so that "not a
        project file" and "a project file that will not read" stay two
        different sentences - the CSV case in particular, which is the desktop
        app's job.
        """
        before = self.snapshot()

        response = self.post(
            "/projects/import", files=self.upload("items.csv", b"id,name\n1,Item\n")
        )

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/")
        self.assertEqual(query, {"form": "import", "error": "type"})
        self.assertEqual(self.snapshot(), before)

    def test_a_pairrank_that_will_not_read_is_refused_with_the_other_sentence(self):
        """Test that an unreadable project is a different refusal from a CSV."""
        before = self.snapshot()

        response = self.post(
            "/projects/import", files=self.upload("Junk.pairrank", b"{ not json")
        )

        _, query = self.redirect_of(response)
        self.assertEqual(query, {"form": "import", "error": "unreadable"})
        self.assertEqual(self.snapshot(), before)

    def test_importing_nothing_asks_for_a_file(self):
        """Test that pressing Import with no file chosen is not an error page."""
        before = self.snapshot()

        response = self.post("/projects/import", files=self.upload("", b""))

        _, query = self.redirect_of(response)
        self.assertEqual(query, {"form": "import", "error": "empty"})
        self.assertEqual(self.snapshot(), before)

    def test_a_file_too_large_to_be_a_project_is_refused(self):
        """
        Test that an oversized upload is turned away rather than read.

        The limit itself is patched down rather than uploaded past: what is
        being checked is that the route stops at it, and a real 32 MB multipart
        body would put half a minute into the suite to check the same
        comparison.
        """
        before = self.snapshot()

        with patch("src.web.routes.projects.MAX_IMPORT_BYTES", 64):
            response = self.post(
                "/projects/import",
                files=self.upload("Big.pairrank", self.good_bytes()),
            )

        _, query = self.redirect_of(response)
        self.assertEqual(query, {"form": "import", "error": "size"})
        self.assertEqual(self.snapshot(), before)

    def test_the_import_limit_is_far_larger_than_any_real_project(self):
        """Test that the guard is a guard rather than a cap on ordinary use."""
        self.assertGreater(MAX_IMPORT_BYTES, 1024 * 1024)

    def test_a_refused_import_reopens_the_form_carrying_the_reason(self):
        """Test that the redirect's error code is drawn as a sentence."""
        body = self.client.get("/?form=import&error=type").text

        self.assertIn('hx-get="/projects/import/callout?error=type"', body)
        self.assertIn(
            IMPORT_ERRORS["type"],
            self.client.get("/projects/import/callout?error=type").text,
        )

    def test_an_invented_error_code_is_ignored(self):
        """Test that a query nobody wrote cannot put words on the screen."""
        body = self.client.get("/?form=import&error=%3Cscript%3E").text

        self.assertIn('hx-get="/projects/import/callout"', body)
        self.assertNotIn("<script>alert", body)


class TestOpenProject(RegisterTestCase):
    """
    Test cases for the one action that can fail on a file the register liked.

    The register's probe checks the top level of a file and stops there, so a
    project whose *item entries* are malformed is listed as openable and is
    not. That failure has to reach the damaged-file page rather than a
    traceback, and it is the reason Open really opens the project instead of
    trusting the tag on the row.
    """

    def seed(self):
        """Put every condition Open can meet in the directory."""
        self.write_project("Alpha.pairrank", name="Alpha")
        self.write_project("Ancient.pairrank", name="Ancient", version=1)
        self.write_project("Future.pairrank", name="Future", version=FUTURE_VERSION)
        self.write_raw("Broken.pairrank", "{ not json at all")

        # Shaped like a project at the top level - a name, two lists of
        # objects - and not a project one level down, where an item has no
        # name. This is exactly the file the probe cannot judge.
        deep = project_data(name="Shallow")
        deep["items"] = [{"id": "item-1", "description": "no name here"}]
        self.write_raw("Shallow.pairrank", deep)

    def test_opening_goes_to_the_project_s_first_sheet(self):
        """Test that Open leads to a screen rather than back to the register."""
        response = self.client.get(
            "/projects/Alpha.pairrank/open", follow_redirects=False
        )

        path, query = self.redirect_of(response)
        self.assertEqual(path, f"/projects/Alpha.pairrank/{DEFAULT_SHEET}")
        self.assertEqual(query, {})

    def test_opening_an_old_format_file_migrates_it_and_keeps_the_original(self):
        """Test that the upgrade the row promised is the upgrade that happens."""
        response = self.client.get(
            "/projects/Ancient.pairrank/open", follow_redirects=False
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn(
            "Ancient.pairrank.v1.bak", {p.name for p in self.data_dir.iterdir()}
        )
        migrated = json.loads((self.data_dir / "Ancient.pairrank").read_text("utf-8"))
        self.assertEqual(migrated["format_version"], CURRENT_FORMAT_VERSION)

    def test_a_file_the_register_called_ok_can_still_fail_to_open(self):
        """
        Test that the shallow probe's blind spot lands on the damaged page.

        The row carries no tag, because the top level of the file is right.
        Opening it is where the truth comes out, and it comes out as a page
        that names the file and points at the backups beside it.
        """
        row = row_of(self.client.get("/").text, "Shallow.pairrank")
        self.assertNotIn('class="tag"', row)

        response = self.client.get("/projects/Shallow.pairrank/open")

        self.assertEqual(response.status_code, DAMAGED_STATUS)
        self.assertIn("damaged", response.text)
        self.assertIn(".pairrank.bak", response.text)

    def test_opening_a_file_that_will_not_parse_is_damage(self):
        """Test that the plainly broken file reaches the same page."""
        response = self.client.get("/projects/Broken.pairrank/open")

        self.assertEqual(response.status_code, DAMAGED_STATUS)
        self.assertIn("damaged", response.text)
        self.assertNotIn("newer version", response.text)

    def test_opening_a_newer_format_file_asks_for_a_newer_application(self):
        """Test that an intact file from the future is not called damaged."""
        response = self.client.get("/projects/Future.pairrank/open")

        self.assertEqual(response.status_code, NEWER_FORMAT_STATUS)
        self.assertIn("newer version", response.text)
        self.assertNotIn("damaged", response.text)

    def test_opening_a_project_that_is_not_there_is_not_found(self):
        """Test that a stale row leads to the not-found page."""
        response = self.client.get("/projects/Missing.pairrank/open")

        self.assertEqual(response.status_code, 404)

    def test_an_id_reaching_out_of_the_directory_is_refused(self):
        """Test that Open is not a way to load an arbitrary path."""
        with self.assertLogs("src.web.registry", "WARNING"):
            response = self.client.get("/projects/notes.txt/open")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.get("/projects/..%2Fsecrets.pairrank/open").status_code, 404
        )


class TestStartupMigration(RegisterTestCase):
    """
    Test cases for the legacy CSV data the web app inherits.

    The desktop app has migrated a directory of ``items.csv``/``votes.csv`` on
    startup since the ``.pairrank`` format arrived, and the web app is often
    pointed at the very same directory over a share. Without this, a user who
    moved to the web frontend would open the register and find nothing, with
    their items and votes sitting unlisted beside it.
    """

    def write_legacy(self, items=3, votes=2) -> None:
        """
        Write a directory of the old CSV files.

        Args:
            items: How many items to write.
            votes: How many votes to write, all between the first two items.
        """
        with open(self.data_dir / "items.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LegacyCsvStorage.ITEMS_FIELDNAMES)
            writer.writeheader()
            for n in range(1, items + 1):
                writer.writerow(
                    {
                        "id": f"item-{n}",
                        "name": f"Item {n}",
                        "identifier": str(n),
                        "description": "",
                    }
                )
        with open(self.data_dir / "votes.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LegacyCsvStorage.VOTES_FIELDNAMES)
            writer.writeheader()
            for n in range(1, votes + 1):
                writer.writerow(
                    {
                        "id": f"vote-{n}",
                        "winner_id": "item-1",
                        "loser_id": "item-2",
                        "timestamp": "2024-01-10T10:00:00",
                        "weight": "2.0",
                    }
                )

    def test_a_directory_of_csv_files_becomes_a_project_on_the_register(self):
        """Test that the old data is listed rather than invisible."""
        self.write_legacy()
        app = create_app(config_for(self.data_dir))

        body = TestClient(app).get("/").text

        row = row_of(body, "project.pairrank")
        self.assertNotEqual(row, "")
        self.assertIn(">3</td>", row)
        self.assertIn(">2</td>", row)

    def test_the_old_files_are_left_where_they_are(self):
        """
        Test that migrating does not clean up behind itself.

        This process is not necessarily the only thing reading that share.
        """
        self.write_legacy()
        create_app(config_for(self.data_dir))

        self.assertTrue((self.data_dir / "items.csv").is_file())
        self.assertTrue((self.data_dir / "votes.csv").is_file())

    def test_a_directory_that_already_has_a_project_is_left_alone(self):
        """Test that the migration runs once and then never again."""
        self.write_legacy()
        self.write_project("Alpha.pairrank", name="Alpha")

        create_app(config_for(self.data_dir))

        self.assertEqual(self.listed(), {"Alpha.pairrank"})

    def test_a_directory_with_no_old_files_is_not_touched(self):
        """Test that the usual case writes nothing at all."""
        create_app(config_for(self.data_dir))

        self.assertEqual(self.listed(), set())

    def test_a_migration_that_fails_does_not_stop_the_server(self):
        """
        Test that a migration that will not run does not take the share down.

        A server that refuses to start over one stray legacy file is a server
        that has taken every other project in the directory with it, so the
        failure is logged and swallowed. The failure is injected because the
        legacy loader is forgiving by design - it skips a row it cannot read
        rather than raising - and what is under test here is the swallow.
        """
        self.write_legacy()

        with patch(
            "src.web.app.StorageMigration.migrate",
            side_effect=OSError("the share went away"),
        ):
            with self.assertLogs("src.web.app", "WARNING") as logged:
                app = create_app(config_for(self.data_dir))

        self.assertIn("the share went away", logged.output[0])
        self.assertEqual(TestClient(app).get("/").status_code, 200)


class TestRegisterUnderARootPath(RegisterTestCase):
    """
    Test cases for running behind a reverse proxy on a subpath.

    Every address on this screen is composed rather than written by hand, so
    the prefix is either on all of them or on none of them. A register whose
    rows point above the proxy's subpath is a front door that opens onto the
    proxy's 404.
    """

    root_path = "/rank"

    def seed(self):
        """Put one project in the directory."""
        self.write_project("Alpha.pairrank", name="Alpha")

    def test_a_row_s_callout_is_fetched_from_under_the_prefix(self):
        """Test that the htmx hookup carries the subpath."""
        row = row_of(self.client.get("/rank/").text, "Alpha.pairrank")

        self.assertIn('hx-get="/rank/projects/Alpha.pairrank/callout"', row)

    def test_the_title_block_s_forms_post_under_the_prefix(self):
        """Test that New and Import do not aim above the proxy's subpath."""
        body = self.client.get("/rank/").text

        self.assertIn('action="/rank/"', body)

    def test_a_callout_s_actions_carry_the_prefix(self):
        """Test that the fragment's own addresses are built the same way."""
        body = self.client.get("/rank/projects/Alpha.pairrank/callout").text

        self.assertIn('href="/rank/projects/Alpha.pairrank/open"', body)
        self.assertIn('href="/rank/projects/Alpha.pairrank/download"', body)

    def test_a_mutation_redirects_back_under_the_prefix(self):
        """Test that a 303 does not send the browser out of the subpath."""
        response = self.post("/rank/projects/new", data={"name": "Keyswitches"})

        path, query = self.redirect_of(response)
        self.assertEqual(path, "/rank/")
        self.assertEqual(query, {"selected": "Keyswitches.pairrank", "done": "created"})

    def test_opening_redirects_to_the_screen_under_the_prefix(self):
        """Test that Open leads to a sheet the proxy actually serves."""
        response = self.client.get(
            "/rank/projects/Alpha.pairrank/open", follow_redirects=False
        )

        path, _ = self.redirect_of(response)
        self.assertEqual(path, f"/rank/projects/Alpha.pairrank/{DEFAULT_SHEET}")


class TestAwkwardFileNames(RegisterTestCase):
    """
    Test cases for file names that are not URLs.

    Names come from the filesystem, not from this application: the desktop app
    saves wherever its file dialog is pointed, so ``Cost #1.pairrank`` is a
    project someone really has. Written into an href unencoded, everything from
    the ``#`` onwards would be dropped, and a ``%`` would be read as the start
    of an escape.
    """

    HASH_NAME = "Cost #1.pairrank"
    PERCENT_NAME = "50%25 Off.pairrank"

    def seed(self):
        """Put two awkwardly named projects in the directory."""
        self.write_project(self.HASH_NAME, name="Cost #1")
        self.write_project(self.PERCENT_NAME, name="50% Off")

    def test_a_row_addresses_its_file_as_one_encoded_segment(self):
        """Test that the hash and the percent survive being written into a URL."""
        body = self.client.get("/").text

        self.assertIn(
            'hx-get="/projects/Cost%20%231.pairrank/callout"',
            row_of(body, self.HASH_NAME),
        )
        self.assertIn(
            'hx-get="/projects/50%2525%20Off.pairrank/callout"',
            row_of(body, self.PERCENT_NAME),
        )

    def test_the_encoded_address_reaches_the_file_it_names(self):
        """Test that what the row asks for is what the route answers about."""
        body = self.client.get("/projects/Cost%20%231.pairrank/callout").text

        self.assertIn("Cost #1", body)
        self.assertIn('href="/projects/Cost%20%231.pairrank/open"', body)

    def test_an_awkward_name_opens(self):
        """
        Test that the whole name reaches the screen the project opens on.

        The Location header is encoded, not spelt out: a bare ``#`` in it would
        be read as a fragment and the browser would ask for ``/projects/Cost``.
        """
        response = self.client.get(
            "/projects/Cost%20%231.pairrank/open", follow_redirects=False
        )

        path, _ = self.redirect_of(response)
        self.assertEqual(path, f"/projects/Cost%20%231.pairrank/{DEFAULT_SHEET}")

    def test_an_awkward_name_downloads_under_its_own_name(self):
        """Test that the header names the file without the quotes closing it."""
        response = self.client.get("/projects/Cost%20%231.pairrank/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, (self.data_dir / self.HASH_NAME).read_bytes())
        self.assertIn(
            'filename="Cost #1.pairrank"', response.headers["content-disposition"]
        )

    def test_a_mutation_selects_an_awkward_name_when_it_comes_back(self):
        """
        Test that the selected row's id survives the redirect's query.

        A duplicate is the only mutation that can produce such a name, because
        New sanitizes what it is given.
        """
        response = self.post(
            "/projects/Cost%20%231.pairrank/duplicate", data={"name": "Cost #2"}
        )

        _, query = self.redirect_of(response)
        self.assertEqual(query["selected"], "Cost _2.pairrank")


if __name__ == "__main__":
    unittest.main()
