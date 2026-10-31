"""Route tests for the History sheet: every vote, and correcting one.

The fixture is the Rankings sheet's: eight items and fifteen votes, ``v0`` the
first cast and ``v14`` the last. Which outcome a station means, and whether a
correction kept the vote's date, are read back from the file, never from the
page.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from src.data.project_storage import ProjectStorage
from src.web.app import create_app
from src.web.routes.history import HISTORY_SHOWN, NOTES, NOTE_GONE, NOTE_SAME, NOTE_STALE
from tests.test_web_items import row_ids
from tests.test_web_projects import config_for, row_of, silence
from tests.test_web_rankings import ITEMS, PROJECT, VOTES, project_data, vote


HISTORY_URL = f"/projects/{PROJECT}/history"


class HistoryTestCase(unittest.TestCase):
    """Base case giving each test an application over a seeded directory."""

    root_path = ""

    def setUp(self):
        """Build an application over a data directory :meth:`seed` filled."""
        silence(self, "src.web.registry", "src.web.app", "src.web.routes.history")
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        self.seed()
        self.app = create_app(config_for(self.data_dir, self.root_path))
        self.client = TestClient(self.app, root_path=self.root_path)

    def tearDown(self):
        """Remove the data directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def seed(self):
        """Write the one project every test here draws."""
        self.write(project_data())

    def write(self, data: dict) -> None:
        """
        Write the project file.

        Args:
            data: The project dictionary.
        """
        (self.data_dir / PROJECT).write_text(json.dumps(data), encoding="utf-8")

    def sheet(self, query: str = "") -> str:
        """
        Draw the History sheet at one address.

        Args:
            query: The query string, without its "?".

        Returns:
            str: The page, after asserting it was drawn.
        """
        response = self.client.get(f"{HISTORY_URL}?{query}" if query else HISTORY_URL)
        self.assertEqual(response.status_code, 200)
        return response.text

    def votes(self) -> list:
        """
        Read the votes back from the file.

        Returns:
            list: The project's votes, in the order they were cast.
        """
        return ProjectStorage.load(self.data_dir / PROJECT).votes

    def post(self, path: str, **data):
        """
        Post a form without following the redirect.

        Args:
            path: The path under the sheet, e.g. ``v3/revise``.
            **data: The form's fields.

        Returns:
            tuple: The redirect's path and its query as single values.
        """
        response = self.client.post(
            f"{HISTORY_URL}/{path}", data=data, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        parsed = urlparse(response.headers["location"])
        return parsed.path, {k: v[0] for k, v in parse_qs(parsed.query).items()}

    def revise(self, vote_id: str, outcome: str, **view):
        """
        Post the revise form as it is drawn for the vote now on file.

        Args:
            vote_id: The vote.
            outcome: The station, ``a3`` .. ``b3``.
            **view: View fields the form carries.

        Returns:
            tuple: As :meth:`post`.
        """
        current = next(v for v in self.votes() if v.id == vote_id)
        return self.post(
            f"{vote_id}/revise", outcome=outcome, recorded=current.winner_id, **view
        )


class TestTheListing(HistoryTestCase):
    """Test cases for the rows and the filters."""

    def test_every_vote_is_listed_newest_first(self):
        """Test the order, and the R numbers Compare uses."""
        body = self.sheet()

        self.assertEqual(row_ids(body), [f"v{i}" for i in reversed(range(len(VOTES)))])
        self.assertIn('<span class="bom-rank">R15</span>', row_of(body, "v14"))
        self.assertIn('<span class="bom-rank">R1</span>', row_of(body, "v0"))

    def test_a_row_names_the_winner_first_with_its_strength(self):
        """Test the sentence and the strength in Compare's words."""
        row = row_of(self.sheet(), "v0")

        self.assertIn('<span class="bom-name">Gateron Oil King</span>', row)
        self.assertIn('<span class="bom-desc">over NovelKeys Cream</span>', row)
        self.assertIn("Much better", row)

    def test_filtering_by_an_item_draws_only_its_votes(self):
        """Test the Item control's address."""
        ids = row_ids(self.sheet("item=boba"))

        expected = [v["id"] for v in VOTES if "boba" in (v["winner_id"], v["loser_id"])]
        self.assertEqual(ids, list(reversed(expected)))

    def test_filtering_by_a_pair_draws_only_their_votes(self):
        """Test the address a Rankings record links to."""
        self.assertEqual(row_ids(self.sheet("item=oil&vs=cream")), ["v13", "v0"])

    def test_the_against_control_lists_only_opponents_met(self):
        """Test that Against offers the item's opponents and nothing else."""
        body = self.sheet("item=quiet")

        cell = re.search(r'id="vs-cell".*?</div>\s*</div>', body, re.S).group(0)
        self.assertEqual(re.findall(r'<option value="([^"]*)"', cell), [""])

    def test_against_is_disabled_until_an_item_is_chosen(self):
        """Test that the opponent control waits for an item."""
        cell = re.search(r'<select[^>]*id="vs"[^>]*>', self.sheet()).group(0)

        self.assertIn("disabled", cell)

    def test_a_stale_filter_draws_every_vote(self):
        """Test that an item that is not there filters nothing."""
        self.assertEqual(len(row_ids(self.sheet("item=missing&vs=oil"))), len(VOTES))

    def test_a_pair_never_compared_says_so(self):
        """Test the empty state for a pair with no votes."""
        body = self.sheet("item=oil&vs=quiet")

        self.assertEqual(row_ids(body), [])
        self.assertIn("Gateron Oil King and Zeal Healios have not been compared.", body)

    def test_a_project_without_votes_points_at_compare(self):
        """Test the empty state of a fresh project."""
        self.write(project_data(votes=[]))

        body = self.sheet()

        self.assertIn("No votes yet.", body)
        self.assertIn(f'href="/projects/{PROJECT}/compare"', body)

    def test_a_long_history_shows_the_newest_and_offers_the_rest(self):
        """Test the cap and Show all."""
        many = [vote(i, "oil", "cream", 1) for i in range(HISTORY_SHOWN + 5)]
        self.write(project_data(votes=many))

        capped = self.sheet()
        self.assertEqual(len(row_ids(capped)), HISTORY_SHOWN)
        self.assertEqual(row_ids(capped)[0], f"v{HISTORY_SHOWN + 4}")
        self.assertIn(f"Newest {HISTORY_SHOWN} shown", capped)
        self.assertIn(f"All {HISTORY_SHOWN + 5}", capped)

        self.assertEqual(len(row_ids(self.sheet("all=1"))), HISTORY_SHOWN + 5)

    def test_a_revised_vote_carries_its_tag(self):
        """Test the REVISED tag on a corrected row."""
        self.revise("v3", "b1")

        self.assertIn('<span class="tag">Revised</span>', row_of(self.sheet(), "v3"))
        self.assertNotIn('<span class="tag">Revised</span>', row_of(self.sheet(), "v2"))

    def test_no_tab_is_current_and_the_way_back_is_there(self):
        """Test that History is not one of the four tabs."""
        body = self.sheet()

        self.assertNotIn('aria-current="page"', body)
        self.assertIn('class="sheet-back"', body)


class TestTheCallouts(HistoryTestCase):
    """Test cases for a row's callout and the revise form."""

    def test_a_row_s_callout_offers_revise_with_no_key(self):
        """Test that nothing but a press reaches the form."""
        body = self.client.get(f"{HISTORY_URL}/v3/callout").text

        self.assertIn("Revise R4…", body)
        self.assertIn(f'hx-get="{HISTORY_URL}/v3/revise"', body)
        self.assertNotIn("data-sheet-key", body)
        self.assertNotIn("aria-keyshortcuts", body)

    def test_a_just_revised_vote_s_callout_offers_restore(self):
        """Test Restore beside the row on a phone, where the cell is far below."""
        self.assertNotIn("/v3/restore", self.client.get(f"{HISTORY_URL}/v3/callout").text)

        self.revise("v3", "b2")

        self.assertIn(
            f'action="{HISTORY_URL}/v3/restore"',
            self.client.get(f"{HISTORY_URL}/v3/callout").text,
        )
        self.assertNotIn("/restore", self.client.get(f"{HISTORY_URL}/v4/callout").text)

    def test_the_form_marks_what_is_on_file(self):
        """Test that the recorded station is checked and the winner is A."""
        body = self.client.get(f"{HISTORY_URL}/v3/revise").text

        checked = re.findall(r'<input type="radio" name="outcome" value="([ab]\d)"[^>]* checked', body)
        self.assertEqual(checked, ["a1"])
        self.assertIn("On file: Gateron Oil King over Cherry MX Red · Slightly better.", body)
        self.assertIn('name="recorded" value="oil"', body)

    def test_the_form_has_six_stations_and_no_equal(self):
        """Test the scale: three each side, and Withdraw instead of Equal."""
        body = self.client.get(f"{HISTORY_URL}/v3/revise").text

        self.assertEqual(
            re.findall(r'name="outcome" value="([ab]\d)"', body),
            ["a3", "a2", "a1", "b1", "b2", "b3"],
        )
        self.assertIn(f'formaction="{HISTORY_URL}/v3/withdraw"', body)

    def test_only_cancel_declares_a_key(self):
        """Test that Issue revision and Withdraw claim no key."""
        body = self.client.get(f"{HISTORY_URL}/v3/revise").text

        self.assertEqual(re.findall(r'data-sheet-key="([^"]+)"', body), ["Escape"])

    def test_an_unknown_vote_has_no_callout(self):
        """Test the 404 for a vote that is not in the file."""
        self.assertEqual(self.client.get(f"{HISTORY_URL}/missing/callout").status_code, 404)
        self.assertEqual(self.client.get(f"{HISTORY_URL}/missing/revise").status_code, 404)


class TestRevising(HistoryTestCase):
    """Test cases for the posts that change a vote, and Restore."""

    def test_revising_flips_the_winner_and_keeps_the_date(self):
        """Test the correction as the file has it."""
        before = {v.id: v for v in self.votes()}

        path, query = self.revise("v3", "b2", item="oil")

        self.assertEqual(path, HISTORY_URL)
        self.assertEqual(
            query, {"selected": "v3", "done": "revised", "vote": "v3", "item": "oil"}
        )
        after = {v.id: v for v in self.votes()}
        self.assertEqual((after["v3"].winner_id, after["v3"].loser_id), ("red", "oil"))
        self.assertEqual(after["v3"].weight, 2.0)
        self.assertEqual(after["v3"].timestamp, before["v3"].timestamp)
        self.assertIsNotNone(after["v3"].revised_at)
        self.assertEqual([v.id for v in self.votes()], [v["id"] for v in VOTES])

    def test_the_sheet_says_what_changed_and_offers_restore(self):
        """Test the Last change sentence after a revision."""
        self.revise("v3", "b2")

        body = self.sheet("selected=v3&done=revised&vote=v3")

        self.assertIn(
            "Revised R4: Cherry MX Red over Gateron Oil King · Better "
            "(was Gateron Oil King over Cherry MX Red · Slightly better)",
            body,
        )
        self.assertIn(f'action="{HISTORY_URL}/v3/restore"', body)

    def test_restore_puts_the_old_vote_back(self):
        """Test Restore after a revision."""
        original = next(v for v in self.votes() if v.id == "v3")
        self.revise("v3", "b2")

        _, query = self.post("v3/restore")

        self.assertEqual(query["done"], "restored")
        restored = next(v for v in self.votes() if v.id == "v3")
        self.assertTrue(restored.is_unchanged_from(original))

    def test_restore_is_offered_only_for_the_last_change(self):
        """Test that a later change takes Restore away from an earlier one."""
        self.revise("v3", "b2")
        self.revise("v4", "b1")

        self.assertNotIn("/v3/restore", self.sheet("done=revised&vote=v3"))
        _, query = self.post("v3/restore")

        self.assertEqual(query["note"], NOTE_STALE)
        self.assertEqual(next(v for v in self.votes() if v.id == "v3").winner_id, "red")

    def test_withdrawing_removes_the_vote_and_restore_returns_it(self):
        """Test Withdraw, and Restore putting the vote back in its place."""
        _, query = self.post("v3/withdraw")

        self.assertEqual(query, {"done": "withdrawn", "vote": "v3"})
        self.assertNotIn("v3", [v.id for v in self.votes()])
        self.assertIn("Withdrew R4: Gateron Oil King over Cherry MX Red", self.sheet("done=withdrawn&vote=v3"))

        self.post("v3/restore")

        self.assertEqual([v.id for v in self.votes()], [v["id"] for v in VOTES])

    def test_choosing_what_is_on_file_changes_nothing(self):
        """Test that an unchanged outcome is not a revision."""
        _, query = self.revise("v3", "a1")

        self.assertEqual(query["note"], NOTE_SAME)
        self.assertIsNone(next(v for v in self.votes() if v.id == "v3").revised_at)
        self.assertIn(NOTES[NOTE_SAME], self.sheet(f"note={NOTE_SAME}"))

    def test_a_form_drawn_before_another_revision_is_refused(self):
        """Test that stations drawn against an old winner are not misread."""
        self.revise("v3", "b2")

        _, query = self.post("v3/revise", outcome="a3", recorded="oil")

        self.assertEqual(query["note"], NOTE_STALE)
        self.assertEqual(next(v for v in self.votes() if v.id == "v3").winner_id, "red")

    def test_a_station_that_is_not_one_is_refused(self):
        """Test an outcome outside the six."""
        _, query = self.post("v3/revise", outcome="a7", recorded="oil")

        self.assertEqual(query["note"], NOTE_STALE)
        self.assertIsNone(next(v for v in self.votes() if v.id == "v3").revised_at)

    def test_a_vote_that_has_gone_changes_nothing(self):
        """Test posts about a vote no longer in the file."""
        _, revised = self.post("missing/revise", outcome="a1", recorded="oil")
        _, withdrawn = self.post("missing/withdraw")

        self.assertEqual(revised, {"note": NOTE_GONE})
        self.assertEqual(withdrawn, {"note": NOTE_GONE})
        self.assertEqual(len(self.votes()), len(VOTES))


class TestTheWaysIn(HistoryTestCase):
    """Test cases for the links from Compare and Rankings."""

    def test_compare_s_revisions_box_links_to_history(self):
        """Test the quiet link beside Revisions."""
        body = self.client.get(f"/projects/{PROJECT}/compare").text

        self.assertIn(f'<a class="rev-history" href="{HISTORY_URL}">', body)

    def test_a_rankings_record_links_each_opponent_to_their_votes(self):
        """Test the record's names as links to the pair's history."""
        body = self.client.get(f"/projects/{PROJECT}/rankings/oil/detail").text

        self.assertIn(f'href="{HISTORY_URL}?item=oil&amp;vs=cream"', body)


if __name__ == "__main__":
    unittest.main()
