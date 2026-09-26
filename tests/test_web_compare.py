"""Route tests for the Compare sheet: one pair, the scale, and the receipt.

Every pair on the sheet has an address (``a`` and ``b``), and every mutation is
a form post answered with a 303, so these tests ask for an address or post a
form and look at two things: the address they land on, and the file the post
left behind. The words on the page are the capture pass's business; where a
test does read the page, it cuts out the one element it is about.

The fixture is the Items sheet's (``tests/test_web_items.py``), itself the
register's, for the reasons §5c of the plan gives.
"""

import errno
import html
import json
import re
import unittest
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

from src.app.session import ProjectSession
from src.data.project_storage import ProjectStorage
from src.web.app import DAMAGED_STATUS
from src.web.routes.compare import (
    CAUSE_DENIED,
    CAUSE_FULL,
    CAUSE_WORDS,
    COMPARE_KEYS,
    DONE_UNDONE,
    DONE_VOTED,
    EMPTY_LEADS,
    REFUSED_SAVE,
    REFUSED_STATION,
    REFUSED_STATION_NOTE,
    REFUSED_UNDO_SAVE,
)
from src.app.session import NoPairReason
from tests.test_web_items import ITEMS, ItemsTestCase, item, project_data
from tests.test_web_projects import silence


PROJECT = "Switches.pairrank"
COMPARE_URL = f"/projects/{PROJECT}/compare"

# The fixture's active items, and those of them with a slot. Retired items
# ("blue", "red") are never offered.
ACTIVE = {"brown", "jade", "oil", "cream", "alpaca"}
SLOTTED = {"jade", "oil", "cream"}

# Two votes a few minutes apart, the latest last, at a time the receipt can
# be read against.
EARLIER = datetime(2026, 9, 16, 21, 3)


def vote(winner: str, loser: str, vote_id: str, weight: float = 2.0, minutes: int = 0) -> dict:
    """
    Build one vote entry.

    Args:
        winner: The winning item's id.
        loser: The losing item's id.
        vote_id: The vote's id.
        weight: Its weight.
        minutes: How long after EARLIER it was cast.

    Returns:
        dict: The entry.
    """
    return {
        "id": vote_id,
        "winner_id": winner,
        "loser_id": loser,
        "weight": weight,
        "timestamp": (EARLIER + timedelta(minutes=minutes)).isoformat(),
    }


VOTES = [
    vote("jade", "cream", "v1", weight=1.0),
    vote("oil", "jade", "v2", weight=2.0, minutes=1),
]


def element(body: str, pattern: str) -> str:
    """
    Cut one element, opening tag to its closing tag, out of a page.

    Args:
        body: The rendered page.
        pattern: A regular expression matching the start of the element; its
            tag name is taken from the first word.

    Returns:
        str: The element, or an empty string. Not nesting-aware: used only on
        elements that hold no element of their own kind.
    """
    tag = re.match(r"<(\w+)", pattern).group(1)
    match = re.search(pattern + rf".*?</{tag}>", body, re.S)
    return match.group(0) if match else ""


def text_of(fragment: str) -> str:
    """
    Read a fragment's text, tags stripped and whitespace collapsed.

    Args:
        fragment: Some markup.

    Returns:
        str: Its text, entities decoded.
    """
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def pair_of(body: str) -> tuple:
    """
    Read the pair a sheet was drawn with, from the fields a vote posts back.

    Args:
        body: The rendered page.

    Returns:
        tuple: The ids in View A and View B.
    """
    form = element(body, r'<form id="vote-form"')
    a = re.search(r'name="a" value="([^"]*)"', form).group(1)
    b = re.search(r'name="b" value="([^"]*)"', form).group(1)
    return (a, b)


def receipt_rows(body: str) -> list:
    """
    List the receipt's rows, oldest first.

    Args:
        body: The rendered page.

    Returns:
        list: Each row's class attribute and text, as (classes, text).
    """
    rows = re.findall(r'<li class="(rev-[^"]*)"[^>]*>(.*?)</li>', body, re.S)
    return [(classes, text_of(inner)) for classes, inner in rows]


class CompareTestCase(ItemsTestCase):
    """Base case: the Items fixture, drawn on the Compare sheet."""

    def setUp(self):
        """Build the application, quietening this sheet's logger too."""
        super().setUp()
        silence(self, "src.web.routes.compare")

    def seed(self):
        """Write the one project every test here compares in."""
        self.write(PROJECT, project_data(votes=VOTES))

    def compare(self, query: str = "") -> str:
        """
        Draw the sheet at one address, which must draw rather than redirect.

        Args:
            query: The query string, without its "?".

        Returns:
            str: The page.
        """
        response = self.client.get(
            f"{COMPARE_URL}?{query}" if query else COMPARE_URL, follow_redirects=False
        )
        self.assertEqual(response.status_code, 200)
        return response.text

    def post(self, action: str, **fields):
        """
        Post one of the sheet's forms without following the redirect.

        Args:
            action: "vote" or "undo".
            **fields: The form's fields.

        Returns:
            The response.
        """
        return self.client.post(
            f"{COMPARE_URL}/{action}", data=fields, follow_redirects=False
        )

    def redirect_of(self, response) -> tuple:
        """
        Take apart a 303.

        Args:
            response: The response, which must be a 303.

        Returns:
            tuple: Its path and its query, as a mapping of single values.
        """
        self.assertEqual(response.status_code, 303)
        parsed = urlparse(response.headers["location"])
        return parsed.path, {key: value[0] for key, value in parse_qs(parsed.query).items()}

    def landed(self, response) -> str:
        """
        Follow a 303 to the page it names.

        Args:
            response: The response.

        Returns:
            str: The page.
        """
        path, _ = self.redirect_of(response)
        location = response.headers["location"]
        self.assertTrue(location.startswith(path))
        page = self.client.get(location, follow_redirects=False)
        self.assertEqual(page.status_code, 200)
        return page.text

    def snapshot(self) -> dict:
        """
        Read every file in the data directory.

        Returns:
            dict: File name to bytes, for "changed nothing" assertions.
        """
        return {
            path.name: path.read_bytes()
            for path in self.data_dir.iterdir()
            if path.is_file()
        }

    def stored(self) -> dict:
        """
        Read the project file as it is on disk.

        Returns:
            dict: The file's JSON.
        """
        return json.loads((self.data_dir / PROJECT).read_text(encoding="utf-8"))

    def stored_votes(self) -> list:
        """
        Read the votes on disk.

        Returns:
            list: Each as (winner, loser, weight).
        """
        return [
            (entry["winner_id"], entry["loser_id"], entry["weight"])
            for entry in self.stored()["votes"]
        ]


class TestTheAddressedPair(CompareTestCase):
    """Test cases for how the sheet's address chooses what it draws."""

    def test_the_bare_sheet_redirects_to_the_session_s_pair(self):
        """Test that no pair in the address means the session chooses one."""
        path, query = self.redirect_of(self.client.get(COMPARE_URL, follow_redirects=False))

        self.assertEqual(path, COMPARE_URL)
        self.assertEqual(set(query), {"a", "b"})
        self.assertLessEqual({query["a"], query["b"]}, ACTIVE)
        self.assertNotEqual(query["a"], query["b"])

    def test_an_addressed_pair_is_drawn_on_the_sides_it_names(self):
        """Test that a and b are View A and View B, both ways round."""
        for a, b in (("oil", "cream"), ("cream", "oil")):
            with self.subTest(a=a, b=b):
                body = self.compare(f"a={a}&b={b}")

                self.assertEqual(pair_of(body), (a, b))
                names = re.findall(r'<h2 class="item-name" id="name-(a|b)">([^<]*)</h2>', body)
                expected = {"oil": "Gateron Oil King", "cream": "NovelKeys Cream"}
                self.assertEqual(names, [("a", expected[a]), ("b", expected[b])])

    def test_a_pair_that_cannot_be_compared_is_chosen_again(self):
        """
        Test the addresses that name no comparable pair.

        The same item twice, an item that does not exist, a retired item, and
        half a pair each redirect to the session's pair, never to an error.
        """
        for query in ("a=oil&b=oil", "a=oil&b=gone", "a=oil&b=blue", "a=oil", "b=oil"):
            with self.subTest(query=query):
                response = self.client.get(f"{COMPARE_URL}?{query}", follow_redirects=False)

                _, landed = self.redirect_of(response)
                self.assertLessEqual({landed["a"], landed["b"]}, ACTIVE)

    def test_a_mistyped_address_draws_the_sheet(self):
        """Test that no parameter can draw FastAPI's 422."""
        body = self.compare("a=oil&b=cream&done=yes&refused=9&x=1")

        self.assertEqual(pair_of(body), ("oil", "cream"))
        self.assertNotIn(REFUSED_STATION_NOTE, body)

    def test_the_register_s_open_lands_on_this_sheet(self):
        """Test that DEFAULT_SHEET is Compare again, as on the desktop."""
        response = self.client.get(f"/projects/{PROJECT}/open")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.url.path, COMPARE_URL)
        self.assertIn("a=", str(response.url))

    def test_an_unknown_project_is_not_found(self):
        """Test the 404 for a project that is not there."""
        response = self.client.get("/projects/Nope.pairrank/compare")

        self.assertEqual(response.status_code, 404)

    def test_a_damaged_project_lands_on_the_damaged_page(self):
        """Test that a file that will not read is not drawn as a pair."""
        self.write("Broken.pairrank", "{ not json")

        response = self.client.get("/projects/Broken.pairrank/compare")

        self.assertEqual(response.status_code, DAMAGED_STATUS)

    def test_two_items_with_one_id_land_on_the_damaged_page(self):
        """Test that the core's refusal reaches the browser as damage, not a loop."""
        twins = [dict(ITEMS[0]), dict(ITEMS[1], id=ITEMS[0]["id"])] + [dict(entry) for entry in ITEMS[2:]]
        self.write("Twins.pairrank", project_data(items=twins))

        for sheet in ("compare", "items"):
            with self.subTest(sheet=sheet):
                response = self.client.get(f"/projects/Twins.pairrank/{sheet}", follow_redirects=False)

                self.assertEqual(response.status_code, DAMAGED_STATUS)


class TestTheSheet(CompareTestCase):
    """Test cases for what one drawn pair carries."""

    def setUp(self):
        """Draw one pair."""
        super().setUp()
        self.body = self.compare("a=oil&b=cream")

    def test_seven_stations_post_their_number(self):
        """Test the scale: one submit button per station, keyed 1 to 7."""
        form = element(self.body, r'<form id="vote-form"')
        stations = re.findall(r'<button class="station"[^>]*value="(\d)"[^>]*aria-keyshortcuts="([^"]*)"', form, re.S)

        self.assertEqual(
            stations,
            [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4 S"), ("5", "5"), ("6", "6"), ("7", "7")],
        )
        self.assertNotIn("disabled", form)

    def test_the_title_block_lists_the_mockup_s_keys(self):
        """Test the keys block, and that Skip and Undo declare their keys."""
        keys = element(self.body, r'<div class="tb-cell tb-keyblock"')
        for legends, verb in COMPARE_KEYS:
            self.assertIn(legends[0], keys)
            self.assertIn(verb, keys)
        self.assertIn('id="skip" aria-keyshortcuts="S"', self.body)
        self.assertIn('id="undo" aria-keyshortcuts="Control+Z"', self.body)

    def test_the_readings_are_the_confidence_reader_s(self):
        """Test that Order settled and Tolerance come from src/app/confidence.py."""
        session = ProjectSession(ProjectStorage.load(self.data_dir / PROJECT))
        reading = session.confidence()

        settled = re.search(r'id="settled">([^<]*)<', self.body).group(1)
        tolerance = re.search(r'id="tolerance">([^<]*)<', self.body).group(1)
        self.assertEqual(settled, f"{reading.settled}/{reading.neighbours}")
        self.assertEqual(tolerance, f"±{round(reading.tolerance)}")

    def test_the_vote_count_and_pairs_compared(self):
        """Test the Votes figure and the selector's pairs compared."""
        self.assertIn('id="votes">2<', self.body)
        # Five active items make ten pairs; two of them have been compared.
        self.assertIn('id="pairs">2 of 10<', self.body)

    def test_the_receipt_is_the_file_s_last_two_votes(self):
        """Test the revision rows: numbered, oldest first, the earlier one muted."""
        rows = receipt_rows(self.body)

        self.assertEqual(
            rows,
            [
                ("rev-row is-previous", "R1 Kailh Box Jade over NovelKeys Cream · Slightly better 21:03"),
                ("rev-row", "R2 Gateron Oil King over Kailh Box Jade · Better 21:04"),
            ],
        )

    def test_the_forms_and_the_mode_cell_address_this_project(self):
        """Test the vote, undo and skip forms, the swap they ask for, and Mode."""
        self.assertIn(f'<form id="vote-form" method="post" action="{COMPARE_URL}/vote" hx-post="{COMPARE_URL}/vote"', self.body)
        self.assertIn(f'action="{COMPARE_URL}/undo" hx-post="{COMPARE_URL}/undo"', self.body)
        self.assertIn(f'method="get" action="{COMPARE_URL}" hx-get="{COMPARE_URL}"', self.body)
        self.assertEqual(self.body.count('hx-select="#frame"'), 3)
        self.assertIn(f'href="/projects/{PROJECT}/settings" id="mode"', self.body)

    def test_the_keys_script_is_outside_the_frame(self):
        """Test that compare.js is loaded once, after the frame htmx swaps."""
        frame_end = self.body.index("</main>")
        script = self.body.index("js/compare.js")

        self.assertGreater(script, frame_end)
        self.assertEqual(self.body.count("js/compare.js"), 1)


class TestAFreshProject(CompareTestCase):
    """Test cases for a project with a pair and no votes yet."""

    def seed(self):
        """Write the project with no votes."""
        self.write(PROJECT, project_data())

    def test_the_readings_have_nothing_to_read(self):
        """Test the dashes, the empty receipt and the disabled Undo."""
        body = self.compare("a=oil&b=cream")

        self.assertIn('id="settled">—<', body)
        self.assertIn('id="tolerance">—<', body)
        self.assertEqual([classes for classes, _ in receipt_rows(body)], ["rev-empty"])
        self.assertRegex(body, r'id="undo" aria-keyshortcuts="Control\+Z" disabled')


class TestNotEnoughItems(CompareTestCase):
    """Test cases for a project that cannot offer a pair."""

    def seed(self):
        """Write a project with one active item and one retired one."""
        self.write(
            PROJECT,
            project_data(items=[item("oil", "Gateron Oil King", slot="10"), item("red", "Red", retired=True)]),
        )

    def test_the_sheet_is_drawn_empty_rather_than_redirected(self):
        """Test the empty state: ghosted views, disabled scale and Skip, the reason."""
        body = self.compare()

        self.assertIn('class="frame-inner is-empty"', body)
        self.assertEqual(body.count('<button class="station"'), 7)
        self.assertEqual(len(re.findall(r'<button class="station"[^>]*disabled>', body, re.S)), 7)
        self.assertRegex(body, r'id="skip" aria-keyshortcuts="S" disabled')
        self.assertRegex(body, r'id="undo" aria-keyshortcuts="Control\+Z" disabled')
        self.assertIn(EMPTY_LEADS[NoPairReason.TOO_FEW_ITEMS], body)
        self.assertIn(f'href="/projects/{PROJECT}/items"', element(body, r'<div class="scale-empty"'))

    def test_an_addressed_pair_does_not_loop(self):
        """Test that a stale pair in the address still ends on the empty sheet."""
        response = self.client.get(f"{COMPARE_URL}?a=oil&b=red", follow_redirects=False)

        self.assertEqual(response.status_code, 200)


class TestBlindedMode(CompareTestCase):
    """Test cases for blinded comparison: slots only, no readings."""

    def seed(self):
        """Write the project, blinded, with votes naming slotted items."""
        self.write(
            PROJECT,
            project_data(votes=VOTES, settings={"blinded_comparison_mode": True}),
        )

    def test_only_slotted_items_are_offered(self):
        """Test the blinded filter on the session's pair and on an address."""
        _, query = self.redirect_of(self.client.get(COMPARE_URL, follow_redirects=False))
        self.assertLessEqual({query["a"], query["b"]}, SLOTTED)

        _, query = self.redirect_of(
            self.client.get(f"{COMPARE_URL}?a=oil&b=brown", follow_redirects=False)
        )
        self.assertLessEqual({query["a"], query["b"]}, SLOTTED)

    def test_the_views_carry_slots_and_nothing_else(self):
        """Test that no name, description or category is in the page at all."""
        body = self.compare("a=oil&b=jade")
        views = element(body, r'<section class="views"')

        self.assertIn('class="frame-inner is-blinded"', body)
        for word in ("Gateron Oil King", "Kailh Box Jade", "Deep, muted.", "Linear", "Clicky"):
            self.assertNotIn(word, views)
        self.assertIn('id="blind-a"', views)
        self.assertIn(">10<", views)
        self.assertIn(">Apostrophe<", views)

    def test_no_reading_is_taken(self):
        """Test that settled order and tolerance are absent, and why is said."""
        body = self.compare("a=oil&b=jade")

        self.assertNotIn('id="settled"', body)
        self.assertNotIn('id="tolerance"', body)
        self.assertNotIn("note-readings", body)
        self.assertIn('class="tb-cell tb-hidden"', body)

    def test_the_receipt_names_slots(self):
        """Test that a revision row says which slot won, not which item."""
        rows = receipt_rows(self.compare("a=oil&b=jade"))

        self.assertEqual(rows[-1][1], "R2 Slot 10 over slot Apostrophe · Better 21:04")
        for _, text in rows:
            self.assertNotIn("Kailh", text)

    def test_too_few_slotted_items_has_its_own_reason(self):
        """Test the blinded empty state: enough items, too few slots."""
        self.write(
            PROJECT,
            project_data(
                items=[item("oil", "Oil", slot="10"), item("brown", "Brown"), item("alpaca", "Alpaca")],
                settings={"blinded_comparison_mode": True},
            ),
        )
        self.client.app.state.registry.forget(PROJECT)

        body = self.compare()

        self.assertIn(EMPTY_LEADS[NoPairReason.BLINDED_NO_IDENTIFIERS], body)


class TestVoting(CompareTestCase):
    """Test cases for a vote: what it writes, and where it lands."""

    def test_each_station_records_its_side_and_weight(self):
        """Test the scale's mapping, station by station, on a fresh project."""
        expected = {
            "1": ("oil", "cream", 3.0),
            "2": ("oil", "cream", 2.0),
            "3": ("oil", "cream", 1.0),
            "5": ("cream", "oil", 1.0),
            "6": ("cream", "oil", 2.0),
            "7": ("cream", "oil", 3.0),
        }
        for station, recorded in expected.items():
            with self.subTest(station=station):
                self.post("vote", a="oil", b="cream", station=station)

                self.assertEqual(self.stored_votes()[-1], recorded)
        self.assertEqual(len(self.stored_votes()), len(VOTES) + 6)

    def test_a_vote_lands_on_the_next_pair_saying_so(self):
        """Test the 303: the session's next pair, done=voted, and which vote."""
        path, query = self.redirect_of(self.post("vote", a="oil", b="cream", station="2"))

        self.assertEqual(path, COMPARE_URL)
        self.assertEqual(query["done"], DONE_VOTED)
        self.assertEqual(query["vote"], self.stored()["votes"][-1]["id"])
        self.assertLessEqual({query["a"], query["b"]}, ACTIVE)

    def test_the_page_it_lands_on_shows_the_new_revision(self):
        """Test that the receipt's latest row is the vote, marked new."""
        page = self.landed(self.post("vote", a="oil", b="cream", station="7"))

        rows = receipt_rows(page)
        self.assertEqual(rows[-1][0], "rev-row is-new")
        self.assertTrue(rows[-1][1].startswith("R3 NovelKeys Cream over Gateron Oil King · Much better"))
        self.assertIn('id="votes">3<', page)

    def test_an_older_vote_s_address_marks_nothing_new(self):
        """Test that done=voted names only the file's last vote."""
        first = self.post("vote", a="oil", b="cream", station="2").headers["location"]
        self.post("vote", a="jade", b="oil", station="2")

        page = self.client.get(first, follow_redirects=False).text

        self.assertNotIn("is-new", page)

    def test_a_restarted_server_marks_nothing_new(self):
        """Test that the mark is the registry's memory, not the address's."""
        location = self.post("vote", a="oil", b="cream", station="2").headers["location"]
        self.client.app.state.registry.forget(PROJECT)

        self.assertNotIn("is-new", self.client.get(location).text)

    def test_the_vote_is_recorded_as_the_last_change(self):
        """
        Test the record_change decision: a vote is the project's last change.

        Items' Last change cell writes its sentence only for its own kinds, so
        after a vote an Items address naming an older edit falls back to the
        modified time - which is right, because the vote came after it.
        """
        self.post("vote", a="oil", b="cream", station="3")

        change = self.client.app.state.registry.open(PROJECT).last_change
        self.assertEqual(change.kind, DONE_VOTED)
        self.assertEqual(change.sides, ("oil", "cream"))
        self.assertEqual(change.vote.winner_id, "oil")

    def test_equal_records_nothing_and_moves_on(self):
        """Test station 4: no vote, a 303 to a pair, the file untouched."""
        before = self.snapshot()

        path, query = self.redirect_of(self.post("vote", a="oil", b="cream", station="4"))

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(path, COMPARE_URL)
        self.assertNotIn("done", query)

    def test_a_station_off_the_scale_is_refused_in_the_page(self):
        """Test that nothing is recorded and the same pair comes back, saying so."""
        before = self.snapshot()
        for station in ("0", "8", "-1", "x", "", "2.5", "nan", "inf"):
            with self.subTest(station=station):
                response = self.post("vote", a="oil", b="cream", station=station)

                _, query = self.redirect_of(response)
                self.assertEqual(query, {"a": "oil", "b": "cream", "refused": REFUSED_STATION})
                self.assertEqual(self.snapshot(), before)
        page = self.landed(self.post("vote", a="oil", b="cream", station="9"))
        self.assertIn(REFUSED_STATION_NOTE, page)

    def test_a_station_is_read_leniently(self):
        """Test that surrounding space and a whole-number spelling are accepted."""
        self.post("vote", a="oil", b="cream", station=" 3 ")
        self.post("vote", a="oil", b="cream", station="6.0")

        self.assertEqual(self.stored_votes()[-2:], [("oil", "cream", 1.0), ("cream", "oil", 2.0)])

    def test_a_vote_on_a_pair_that_cannot_be_compared_records_nothing(self):
        """Test a stale page: an item retired in another tab, or no pair at all."""
        before = self.snapshot()
        for fields in ({"a": "oil", "b": "blue"}, {"a": "oil", "b": "gone"}, {"a": "oil", "b": "oil"}, {}):
            with self.subTest(fields=fields):
                path, query = self.redirect_of(self.post("vote", station="2", **fields))

                self.assertEqual((path, query), (COMPARE_URL, {}))
                self.assertEqual(self.snapshot(), before)

    def test_a_vote_over_a_file_changed_on_disk_keeps_the_other_edit(self):
        """Test that the vote re-reads the file before writing it."""
        self.compare("a=oil&b=cream")  # opened, and cached
        self.write(PROJECT, project_data(items=ITEMS + [item("new", "Desk Added")], votes=VOTES))

        self.post("vote", a="oil", b="cream", station="2")

        self.assertIn("new", {entry["id"] for entry in self.stored()["items"]})
        self.assertEqual(len(self.stored_votes()), len(VOTES) + 1)


class TestUndo(CompareTestCase):
    """Test cases for undo: what it removes, and which pair comes back."""

    def test_undo_removes_the_last_vote_and_re_offers_its_pair(self):
        """Test the file and the 303 after undoing the fixture's last vote."""
        path, query = self.redirect_of(self.post("undo", a="oil", b="cream"))

        self.assertEqual(self.stored_votes(), [("jade", "cream", 1.0)])
        self.assertEqual(path, COMPARE_URL)
        # A vote from a file knows only its winner, who goes in View A.
        self.assertEqual(query, {"a": "oil", "b": "jade", "done": DONE_UNDONE, "vote": "v2"})

    def test_a_vote_undone_here_goes_back_on_the_sides_it_was_drawn_on(self):
        """Test that pressing 7 and undoing it does not swap the views."""
        self.post("vote", a="oil", b="cream", station="7")

        _, query = self.redirect_of(self.post("undo", a="jade", b="brown"))

        self.assertEqual((query["a"], query["b"]), ("oil", "cream"))

    def test_the_page_it_lands_on_strikes_the_vote_through(self):
        """Test the receipt after an undo: the previous vote, then the undone one."""
        page = self.landed(self.post("undo", a="oil", b="cream"))

        rows = receipt_rows(page)
        self.assertEqual(
            rows,
            [
                ("rev-row is-previous", "R1 Kailh Box Jade over NovelKeys Cream · Slightly better 21:03"),
                # The tag's margin spaces it on screen; a visually hidden
                # separator spaces it for a screen reader.
                ("rev-row is-undone", "R2 Gateron Oil King over Kailh Box Jade · Better; Undone · pair re-offered 21:04"),
            ],
        )
        self.assertIn('id="votes">1<', page)

    def test_the_undone_tag_is_heard_apart_from_the_strength(self):
        """Test the separator: hidden from sight, but in the text a reader says."""
        page = self.landed(self.post("undo", a="oil", b="cream"))

        row = element(page, r'<li class="rev-row[^"]*is-undone')
        self.assertIn('</span><span class="visually-hidden">; </span><span class="rev-tag">', row)
        self.assertNotIn("BetterUndone", text_of(row))

    def test_a_pair_that_cannot_come_back_is_not_called_re_offered(self):
        """Test the undo of a vote whose item has been retired since."""
        self.write(
            PROJECT,
            project_data(
                items=[entry if entry["id"] != "jade" else item("jade", "Kailh Box Jade", retired=True) for entry in ITEMS],
                votes=VOTES,
            ),
        )
        self.client.app.state.registry.forget(PROJECT)

        response = self.post("undo", a="oil", b="cream")

        _, query = self.redirect_of(response)
        self.assertNotIn("jade", (query["a"], query["b"]))
        rows = receipt_rows(self.landed(response))
        self.assertEqual(rows[-1][0], "rev-row is-undone")
        self.assertNotIn("re-offered", rows[-1][1])

    def test_nothing_to_undo_goes_back_to_the_pair(self):
        """Test undo on a project with no votes: nothing changes."""
        self.write(PROJECT, project_data())
        self.client.app.state.registry.forget(PROJECT)
        before = self.snapshot()

        _, query = self.redirect_of(self.post("undo", a="oil", b="cream"))

        self.assertEqual(query, {"a": "oil", "b": "cream"})
        self.assertEqual(self.snapshot(), before)

    def test_an_undone_address_after_a_new_vote_strikes_nothing(self):
        """Test that done=undone names only an undo that is still the last change."""
        location = self.post("undo", a="oil", b="cream").headers["location"]
        self.post("vote", a="oil", b="cream", station="2")

        self.assertNotIn("is-undone", self.client.get(location).text)


class TestTheRoundTrip(CompareTestCase):
    """Test cases for a vote and its undo, end to end through the addresses."""

    def test_a_vote_and_its_undo_leave_the_file_as_it_was(self):
        """Test draw, vote, land, undo, land: the same pair back, the votes restored."""
        before = self.stored_votes()
        pair = pair_of(self.compare("a=cream&b=oil"))
        self.assertEqual(pair, ("cream", "oil"))

        voted = self.landed(self.post("vote", a=pair[0], b=pair[1], station="6"))
        self.assertEqual(self.stored_votes(), before + [("oil", "cream", 2.0)])
        self.assertEqual(receipt_rows(voted)[-1][0], "rev-row is-new")
        self.assertIn(f'id="votes">{len(before) + 1}<', voted)

        on_screen = pair_of(voted)
        response = self.post("undo", a=on_screen[0], b=on_screen[1])
        _, query = self.redirect_of(response)
        self.assertEqual((query["a"], query["b"]), pair)
        self.assertEqual(query["done"], DONE_UNDONE)
        undone = self.landed(response)
        self.assertEqual(pair_of(undone), pair)
        self.assertEqual(self.stored_votes(), before)
        self.assertEqual(receipt_rows(undone)[-1][0], "rev-row is-undone")

    def test_undo_re_offers_the_same_pair_whichever_page_it_is_pressed_on(self):
        """Test that Undo names the vote's pair, not the pair on the page it came from."""
        self.post("vote", a="jade", b="oil", station="1")

        for page in (("cream", "alpaca"), ("", ""), ("gone", "oil")):
            with self.subTest(page=page):
                self.post("vote", a="jade", b="oil", station="1")

                _, query = self.redirect_of(self.post("undo", a=page[0], b=page[1]))

                self.assertEqual((query["a"], query["b"]), ("jade", "oil"))


class TestTheBlindedFilter(CompareTestCase):
    """Test cases for blinded mode through the mutations, not just the draw."""

    def seed(self):
        """Write the project, blinded."""
        self.write(
            PROJECT,
            project_data(votes=VOTES, settings={"blinded_comparison_mode": True}),
        )

    def test_a_vote_lands_only_on_slotted_pairs(self):
        """Test the next pair after each of several votes."""
        for station in ("1", "5", "3", "7"):
            with self.subTest(station=station):
                _, query = self.redirect_of(self.post("vote", a="oil", b="jade", station=station))

                self.assertLessEqual({query["a"], query["b"]}, SLOTTED)

    def test_a_vote_on_an_item_with_no_slot_records_nothing(self):
        """Test a page drawn before blinding: its pair is no longer comparable."""
        before = self.snapshot()

        path, query = self.redirect_of(self.post("vote", a="oil", b="brown", station="2"))

        self.assertEqual((path, query), (COMPARE_URL, {}))
        self.assertEqual(self.snapshot(), before)

    def test_undoing_a_vote_on_an_unslotted_item_offers_a_slotted_pair(self):
        """Test undo of a vote from before blinding: not re-offered, a slotted pair instead."""
        self.write(
            PROJECT,
            project_data(
                votes=VOTES + [vote("brown", "oil", "v3", minutes=2)],
                settings={"blinded_comparison_mode": True},
            ),
        )
        self.client.app.state.registry.forget(PROJECT)

        response = self.post("undo", a="oil", b="jade")

        _, query = self.redirect_of(response)
        self.assertLessEqual({query["a"], query["b"]}, SLOTTED)
        self.assertEqual(len(self.stored_votes()), len(VOTES))
        rows = receipt_rows(self.landed(response))
        self.assertEqual(rows[-1][0], "rev-row is-undone")
        self.assertNotIn("re-offered", rows[-1][1])
        self.assertNotIn("Cherry MX Brown", rows[-1][1])


class SaveFailureTestCase(CompareTestCase):
    """Base case with a switch for making every save fail."""

    def fail_saves(self, error: OSError = None):
        """
        Make every save refuse until the test ends.

        Args:
            error: What the save raises; permission denied by default.
        """
        patcher = mock.patch.object(
            ProjectStorage,
            "save",
            side_effect=error or PermissionError(13, "Permission denied"),
        )
        self.addCleanup(patcher.stop)
        patcher.start()


class TestAVoteThatCannotBeSaved(SaveFailureTestCase):
    """Test cases for a vote whose save the file refuses."""

    def test_nothing_is_recorded_and_the_same_pair_comes_back(self):
        """Test the file, and the 303 to the pair with the failure named."""
        self.compare("a=oil&b=cream")
        before = self.snapshot()
        self.fail_saves()

        _, query = self.redirect_of(self.post("vote", a="oil", b="cream", station="6"))

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            query,
            {"a": "oil", "b": "cream", "refused": REFUSED_SAVE, "station": "6", "cause": CAUSE_DENIED},
        )

    def test_the_vote_is_not_left_in_memory(self):
        """Test the 7a gap: the open project holds no vote the file does not."""
        self.fail_saves()
        page = self.landed(self.post("vote", a="oil", b="cream", station="2"))
        mock.patch.stopall()

        self.assertIn(f'id="votes">{len(VOTES)}<', page)
        self.assertEqual(len(self.client.app.state.registry.open(PROJECT).session.project.votes), len(VOTES))
        self.post("vote", a="oil", b="cream", station="2")
        self.assertEqual(len(self.stored_votes()), len(VOTES) + 1)

    def test_the_page_draws_the_warning_and_retry_posts_the_vote_again(self):
        """Test the save-failed state: its class, its warning, and Retry's fields."""
        self.fail_saves()
        page = self.landed(self.post("vote", a="oil", b="cream", station="6"))

        self.assertIn('class="frame-inner is-save-failed"', page)
        self.assertIn("tb-file-text is-warn", page)
        warning = element(page, r'<div class="save-warning"')
        self.assertIn(CAUSE_WORDS[CAUSE_DENIED], text_of(warning))
        retry = element(page, r'<form method="post" action="[^"]*/vote" hx-post')
        self.assertIn('id="retry"', retry)
        self.assertIn('name="station" value="6"', retry)
        self.assertEqual(pair_of(page), ("oil", "cream"))

    def test_retry_records_the_vote_once_the_file_takes_it(self):
        """Test that Retry is the same post as the station was."""
        self.fail_saves()
        _, query = self.redirect_of(self.post("vote", a="oil", b="cream", station="6"))
        mock.patch.stopall()

        self.post("vote", a=query["a"], b=query["b"], station=query["station"])

        self.assertEqual(self.stored_votes()[-1], ("cream", "oil", 2.0))

    def test_a_full_disk_and_an_unnamed_failure(self):
        """Test the cause vocabulary: full, and nothing for anything else."""
        for error, cause in (
            (OSError(errno.ENOSPC, "No space left on device"), CAUSE_FULL),
            (OSError(errno.EIO, "Input/output error"), None),
        ):
            with self.subTest(cause=cause):
                self.fail_saves(error)
                _, query = self.redirect_of(self.post("vote", a="oil", b="cream", station="2"))
                mock.patch.stopall()

                self.assertEqual(query.get("cause"), cause)


class TestAnUndoThatCannotBeSaved(SaveFailureTestCase):
    """Test cases for an undo whose save the file refuses."""

    def test_the_vote_stands_and_the_pair_comes_back(self):
        """Test the file, the memory, and the 303."""
        before = self.snapshot()
        self.fail_saves()

        response = self.post("undo", a="oil", b="cream")

        _, query = self.redirect_of(response)
        self.assertEqual(query, {"a": "oil", "b": "cream", "refused": REFUSED_UNDO_SAVE, "cause": CAUSE_DENIED})
        self.assertEqual(self.snapshot(), before)
        page = self.landed(response)
        self.assertIn(f'id="votes">{len(VOTES)}<', page)
        self.assertIn('class="frame-inner is-save-failed"', page)
        retry = element(page, r'<form method="post" action="[^"]*/undo" hx-post')
        self.assertIn('id="retry"', retry)
        self.assertNotIn('name="station"', retry)


class TestTheSaveFailedAddress(CompareTestCase):
    """Test cases for the save-failed state as an address, for the capture pass."""

    def test_the_address_draws_the_state(self):
        """Test that refused=save alone reproduces the page, with no failure."""
        page = self.compare(f"a=oil&b=cream&refused={REFUSED_SAVE}&station=2&cause={CAUSE_DENIED}")

        self.assertIn("is-save-failed", page)
        self.assertIn('id="retry"', page)

    def test_the_address_prints_nothing_of_its_own(self):
        """Test a cause off the list and a station off the scale."""
        page = self.compare(f"a=oil&b=cream&refused={REFUSED_SAVE}&station=%3Cb%3E&cause=%3Cscript%3E")
        warning = text_of(element(page, r'<div class="save-warning"'))

        self.assertIn("is-save-failed", page)
        self.assertNotIn("script", page.split('id="rev-rows"')[1].split("</section>")[0])
        self.assertIn(f"Couldn’t write {PROJECT}. Nothing was recorded", warning)
        self.assertNotIn('id="retry"', page)

    def test_equal_has_no_retry(self):
        """Test that station 4, which records nothing, is never retried."""
        self.assertNotIn('id="retry"', self.compare(f"a=oil&b=cream&refused={REFUSED_SAVE}&station=4"))

    def test_a_mistyped_refusal_draws_the_plain_sheet(self):
        """Test anything else in refused."""
        page = self.compare("a=oil&b=cream&refused=sav")

        self.assertNotIn("is-save-failed", page)
        self.assertNotIn('class="save-warning"', page)

    def test_the_empty_sheet_draws_no_warning(self):
        """Test a failure address on a project that cannot offer a pair."""
        self.write(PROJECT, project_data(items=[item("oil", "Oil", slot="10")]))
        self.client.app.state.registry.forget(PROJECT)

        page = self.compare(f"refused={REFUSED_SAVE}&station=2")

        self.assertNotIn("is-save-failed", page)


class TestChangedOnDisk(CompareTestCase):
    """Test cases for the notice strip after a vote over a file changed elsewhere."""

    def change_on_disk(self, extra_votes: int = 3) -> None:
        """
        Open the project, then save it from "another program" with more votes.

        Args:
            extra_votes: How many votes the other program added.
        """
        self.compare("a=oil&b=cream")
        more = [vote("jade", "alpaca", f"x{n}", minutes=5 + n) for n in range(extra_votes)]
        self.write(PROJECT, project_data(votes=VOTES + more))

    def notice_of(self, page: str) -> str:
        """
        Cut the notice strip out of a page.

        Args:
            page: The rendered page.

        Returns:
            str: The strip's opening tag and contents.
        """
        return element(page, r'<div class="notice" id="notice"')

    def test_a_plain_page_carries_the_strip_hidden(self):
        """Test that the strip is always drawn, so a swap can carry it."""
        strip = self.notice_of(self.compare("a=oil&b=cream"))

        self.assertIn(" hidden>", strip)
        self.assertNotIn("<p>", strip)

    def test_every_form_carries_the_strip_out_of_band(self):
        """Test the vote, undo and skip forms."""
        page = self.compare("a=oil&b=cream")

        self.assertEqual(page.count('hx-select-oob="#notice"'), 3)

    def test_the_page_a_vote_lands_on_says_so_once(self):
        """Test the notice, its vote count, and that the next page has none."""
        self.change_on_disk()

        response = self.post("vote", a="oil", b="cream", station="2")
        location = response.headers["location"]
        strip = self.notice_of(self.landed(response))

        self.assertNotIn(" hidden>", strip)
        self.assertIn(f"{PROJECT} was saved by another program and has been reloaded: 3 votes added.", text_of(strip))
        self.assertIn("The pair below is new.", strip)
        self.assertIn(" hidden>", self.notice_of(self.client.get(location).text))

    def test_an_htmx_swap_takes_it_too(self):
        """Test that a swapped-in page, which carries the strip out of band, takes it."""
        self.change_on_disk(extra_votes=1)

        location = self.post("vote", a="oil", b="cream", station="2").headers["location"]
        page = self.client.get(location, headers={"HX-Request": "true"}).text

        self.assertIn("reloaded: 1 vote added.", text_of(self.notice_of(page)))

    def test_dismiss_links_to_the_pair(self):
        """Test the no-JavaScript Dismiss: a reload of the pair, which draws no notice."""
        self.change_on_disk()

        page = self.landed(self.post("vote", a="oil", b="cream", station="2"))

        a, b = pair_of(page)
        self.assertRegex(self.notice_of(page), rf'id="notice-dismiss" href="{COMPARE_URL}\?a={a}&amp;b={b}"')

    def test_a_failed_save_over_a_changed_file_keeps_the_pair(self):
        """Test that a reload whose vote then failed does not call the pair new."""
        self.change_on_disk(extra_votes=0)
        with mock.patch.object(ProjectStorage, "save", side_effect=PermissionError(13, "denied")):
            response = self.post("vote", a="oil", b="cream", station="2")
        strip = self.notice_of(self.landed(response))

        self.assertIn("has been reloaded.", strip)
        self.assertNotIn("The pair below is new.", strip)


class TestSkipPassesOverThePair(CompareTestCase):
    """Test cases for Skip and Equal naming the pair on screen."""

    def session_pair(self) -> dict:
        """Ask the bare sheet which pair the session would choose."""
        _, query = self.redirect_of(self.client.get(COMPARE_URL, follow_redirects=False))
        return query

    def test_the_skip_form_names_the_pair_on_screen(self):
        """Test the hidden fields, which are not a/b (those would draw it again)."""
        form = element(self.compare("a=oil&b=cream"), r'<form class="tb-cell tb-skip"')

        self.assertIn('name="skip_a" value="oil"', form)
        self.assertIn('name="skip_b" value="cream"', form)

    def test_skip_and_equal_land_on_another_pair(self):
        """Test that the pair a skip is pressed on is the one pair it will not offer."""
        chosen = self.session_pair()
        a, b = chosen["a"], chosen["b"]
        responses = {
            "skip": self.client.get(f"{COMPARE_URL}?skip_a={a}&skip_b={b}", follow_redirects=False),
            "equal": self.post("vote", a=a, b=b, station="4"),
        }

        for name, response in responses.items():
            with self.subTest(name):
                _, landed = self.redirect_of(response)
                self.assertNotEqual({landed["a"], landed["b"]}, {a, b})
                self.assertLessEqual({landed["a"], landed["b"]}, ACTIVE)

    def test_ids_naming_no_pair_are_ignored(self):
        """Test the lenient read: a pair that cannot be compared excludes nothing."""
        # The fixture's categories make the session's choice a random draw,
        # so what is checked is what the route asked the session for.
        for query in ("skip_a=oil&skip_b=blue", "skip_a=oil&skip_b=oil", "skip_a=oil", "skip_b=%20"):
            with self.subTest(query=query):
                with mock.patch.object(
                    ProjectSession, "skip", autospec=True, side_effect=ProjectSession.skip
                ) as skip:
                    response = self.client.get(f"{COMPARE_URL}?{query}", follow_redirects=False)

                self.redirect_of(response)
                self.assertEqual(skip.call_args.kwargs, {"exclude": None})

    def test_the_pair_on_screen_is_passed_on_as_given(self):
        """Test that a comparable pair reaches the session, from Skip and from Equal."""
        for send in (
            lambda: self.client.get(f"{COMPARE_URL}?skip_a=cream&skip_b=oil", follow_redirects=False),
            lambda: self.post("vote", a="cream", b="oil", station="4"),
        ):
            with mock.patch.object(
                ProjectSession, "skip", autospec=True, side_effect=ProjectSession.skip
            ) as skip:
                self.redirect_of(send())

            self.assertEqual(skip.call_args.kwargs, {"exclude": ("cream", "oil")})


class TestEveryPageReadsTheFile(CompareTestCase):
    """Test cases for a page drawn after the file changed, with no vote between."""

    def test_blinded_mode_switched_on_elsewhere_hides_the_names_at_once(self):
        """Test that the next page is blinded, and an unslotted pair is chosen again."""
        self.compare("a=oil&b=brown")
        self.write(
            PROJECT,
            project_data(votes=VOTES, settings={"blinded_comparison_mode": True}),
        )

        body = self.compare("a=oil&b=cream")

        self.assertIn('class="frame-inner is-blinded"', body)
        for entry in ITEMS:
            self.assertNotIn(html.escape(entry["name"]), body)
        response = self.client.get(f"{COMPARE_URL}?a=oil&b=brown", follow_redirects=False)
        _, landed = self.redirect_of(response)
        self.assertLessEqual({landed["a"], landed["b"]}, SLOTTED)

    def test_the_page_says_the_file_was_reloaded(self):
        """Test that a GET which finds the change takes the notice."""
        self.compare("a=oil&b=cream")
        self.write(PROJECT, project_data(votes=VOTES + [vote("jade", "alpaca", "x1", minutes=9)]))

        strip = element(self.compare("a=oil&b=cream"), r'<div class="notice" id="notice"')

        self.assertIn("reloaded: 1 vote added.", text_of(strip))
        self.assertNotIn("The pair below is new.", strip)

    def test_a_vote_over_a_deleted_file_leaves_the_sheet_not_found(self):
        """Test that the refused vote drops the stale project, so the GET says 404 too."""
        self.compare("a=oil&b=cream")
        (self.data_dir / PROJECT).unlink()

        self.assertEqual(self.post("vote", a="oil", b="cream", station="2").status_code, 404)
        self.assertEqual(self.client.get(f"{COMPARE_URL}?a=oil&b=cream").status_code, 404)

    def test_a_file_replaced_by_a_newer_format_is_refused_on_the_next_page(self):
        """Test the GET after a change the registry cannot load."""
        self.compare("a=oil&b=cream")
        self.write(PROJECT, project_data(votes=VOTES, format_version=99))

        response = self.client.get(f"{COMPARE_URL}?a=oil&b=cream", follow_redirects=False)

        self.assertEqual(response.status_code, 409)


class TestAPairThatCannotBeAddressed(CompareTestCase):
    """Test cases for a session pair that the address cannot draw back."""

    def test_the_sheet_draws_empty_rather_than_redirecting_to_itself(self):
        """Test the guard against a redirect loop."""
        with mock.patch.object(ProjectSession, "offer_pair", return_value=None):
            response = self.client.get(COMPARE_URL, follow_redirects=False)

        self.assertEqual(response.status_code, 200)
        self.assertIn("is-empty", response.text)

    def test_ids_that_do_not_survive_the_address_draw_empty(self):
        """Test ids the address cannot carry back as themselves: a number, nothing, None."""
        # The core turns a number into text and refuses an empty id, so a
        # file cannot bring one; the guard is proved on the open project.
        self.write(PROJECT, project_data(items=[item("p", "Pea"), item("q", "Queue")], slots=[], slot_labels={}))
        self.compare("a=p&b=q")
        project = self.app.state.registry.open(PROJECT).session.project
        for ids in ((1, 2), ("", "q"), (None, "q")):
            with self.subTest(ids=ids):
                for entry, item_id in zip(project.items, ids):
                    entry.id = item_id

                response = self.client.get(COMPARE_URL, follow_redirects=False)

                self.assertEqual(response.status_code, 200)
                self.assertIn("is-empty", response.text)


class TestCompareUnderARootPath(CompareTestCase):
    """Test cases for the sheet behind a reverse proxy on a subpath."""

    root_path = "/rank"

    def test_the_forms_and_the_redirects_carry_the_prefix(self):
        """Test every address the sheet builds, and every 303 it answers."""
        body = self.compare("a=oil&b=cream")
        prefixed = f"/rank{COMPARE_URL}"

        self.assertIn(f'action="{prefixed}/vote"', body)
        self.assertIn(f'action="{prefixed}/undo"', body)
        self.assertIn(f'action="{prefixed}" hx-get="{prefixed}"', body)
        for response in (
            self.client.get(COMPARE_URL, follow_redirects=False),
            self.post("vote", a="oil", b="cream", station="2"),
            self.post("undo", a="oil", b="cream"),
        ):
            with self.subTest(url=str(response.request.url)):
                self.assertTrue(response.headers["location"].startswith(prefixed))


if __name__ == "__main__":
    unittest.main()
