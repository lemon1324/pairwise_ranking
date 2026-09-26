"""Route tests for the Rankings sheet: one project's items in rank order.

Every view of the sheet is an address, so these tests ask for an address and
look at the rows, the detail or the file that came back. The order and every
figure are the core's (``ProjectSession.rankings``), so the expected order is
read from the core too, never written out by hand; the words on the page are
the capture pass's business.

The export's test is the one that matters most: the file the sheet downloads
must be byte for byte the file the desktop's Export button writes for the same
view. It drives the desktop's own widget, offscreen, rather than restating
what that widget does.

The fixture is the Items sheet's (``tests/test_web_items.py``), which is the
register's, for the reasons §5c of the plan gives.
"""

import csv
import html
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from urllib.parse import quote, unquote

from fastapi.testclient import TestClient

from src.app.session import ProjectSession
from src.data.format_version import CURRENT_FORMAT_VERSION
from src.data.project_storage import ProjectStorage
from src.models.export import EXPORT_HEADER
from src.web.app import DAMAGED_STATUS, NEWER_FORMAT_STATUS, create_app
from src.web.routes.rankings import RANKING_KEYS, RECORD_SHOWN, TAG_RETIRED, export_csv
from tests.test_web_items import element, field_of, item, row_ids
from tests.test_web_projects import config_for, row_of, silence


PROJECT = "Switches.pairrank"
RANKINGS_URL = f"/projects/{PROJECT}/rankings"
EXPORT_URL = f"{RANKINGS_URL}/export"

# Two categories, one retired item in each, and one item nobody has voted on.
ITEMS = [
    item("oil", "Gateron Oil King", slot="1", description="Deep, muted."),
    item("cream", "NovelKeys Cream", slot="2"),
    item("alpaca", "Alpaca V2", slot="3"),
    item("brown", "Cherry MX Brown", slot="4", category="Tactile"),
    item("boba", "Gazzew Boba U4T", slot="5", category="Tactile"),
    item("red", "Cherry MX Red", retired=True),
    item("halo", "Drop Halo True", category="Tactile", retired=True),
    item("quiet", "Zeal Healios", slot="6", category="Silent"),
]

# A clear order: Oil King beats everything, Cream beats the rest, and so on
# down; the two retired items sit in the middle of it. Healios has no votes.
BEATS = [
    ("oil", "cream", 3), ("oil", "alpaca", 2), ("oil", "brown", 3), ("oil", "red", 1),
    ("cream", "alpaca", 2), ("cream", "brown", 1), ("cream", "boba", 2),
    ("red", "alpaca", 1), ("red", "boba", 2), ("halo", "boba", 1),
    ("alpaca", "brown", 2), ("alpaca", "halo", 1), ("brown", "boba", 3),
    ("cream", "oil", 1), ("boba", "alpaca", 1),
]


def vote(number: int, winner: str, loser: str, weight: float, days_ago: float = 0.0) -> dict:
    """
    Build one vote entry.

    Args:
        number: Makes the vote's id.
        winner: The winning item's id.
        loser: The losing item's id.
        weight: The vote's weight.
        days_ago: How long before now it was cast.

    Returns:
        dict: The entry.
    """
    return {
        "id": f"v{number}",
        "winner_id": winner,
        "loser_id": loser,
        "weight": weight,
        "timestamp": (datetime.now() - timedelta(days=days_ago)).isoformat(),
    }


VOTES = [vote(i, w, l, weight) for i, (w, l, weight) in enumerate(BEATS)]


def project_data(items=ITEMS, votes=VOTES, half_life=0.0, **extra) -> dict:
    """
    Build a project dictionary for the Rankings sheet.

    Args:
        items: The item entries.
        votes: The vote entries.
        half_life: The decay half-life in days; 0 is no decay, so a raw and a
            decayed weight agree unless a test asks otherwise.
        **extra: Top-level keys to override.

    Returns:
        dict: The project data, ready to be written as JSON.
    """
    data = {
        "format_version": CURRENT_FORMAT_VERSION,
        "name": "Linear switches, winter shortlist",
        "created": "2026-01-01T09:00:00",
        "modified": "2026-09-16T21:04:00",
        "items": list(items),
        "votes": list(votes),
        "settings": {"decay_timescale_days": half_life},
        "slots": [],
        "slot_labels": {},
    }
    data.update(extra)
    return data


def cells_of(row: str) -> list:
    """
    Read a row's cells as text, with hidden words left in and glyphs out.

    Args:
        row: One ``<tr>``.

    Returns:
        list: Each cell's text, whitespace collapsed.
    """
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
    heard = [re.sub(r'<span aria-hidden="true">.*?</span>', "", cell) for cell in cells]
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip() for cell in heard]


def record_of(body: str) -> list:
    """
    Read a detail's weighted record.

    Args:
        body: The detail fragment.

    Returns:
        list: One (opponent, won, lost) tuple per line, as drawn.
    """
    table = re.search(r'<table class="record">.*?</table>', body, re.S)
    if not table:
        return []
    return [tuple(cells_of(row)) for row in re.findall(r"<tr>\s*<td.*?</tr>", table.group(0), re.S)]


class RankingsTestCase(unittest.TestCase):
    """Base case giving each test an application over a seeded directory."""

    root_path = ""

    def setUp(self):
        """Build an application over a data directory :meth:`seed` filled."""
        silence(self, "src.web.registry", "src.web.app", "src.web.routes.rankings")
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
        self.write(PROJECT, project_data())

    def write(self, file_name: str, data) -> Path:
        """
        Write a project file.

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

    def sheet(self, query: str = "") -> str:
        """
        Draw the Rankings sheet at one address.

        Args:
            query: The query string, without its "?".

        Returns:
            str: The page, after asserting it was drawn.
        """
        response = self.client.get(f"{RANKINGS_URL}?{query}" if query else RANKINGS_URL)
        self.assertEqual(response.status_code, 200)
        return response.text

    def detail(self, item_id: str) -> str:
        """
        Fetch one row's detail as the engine does.

        Args:
            item_id: The item.

        Returns:
            str: The fragment, after asserting it was drawn.
        """
        response = self.client.get(
            f"{RANKINGS_URL}/{item_id}/detail", headers={"HX-Request": "true"}
        )
        self.assertEqual(response.status_code, 200)
        return response.text

    def session(self) -> ProjectSession:
        """
        Open the project from its file, as the desktop would.

        Returns:
            ProjectSession: A session of its own, apart from the server's.
        """
        return ProjectSession(ProjectStorage.load(self.data_dir / PROJECT))

    def core_order(self, retired: bool = False, category: str = "") -> list:
        """
        List the ids the core ranks, in its order.

        Args:
            retired: Whether retired items are included.
            category: The one category to keep, or empty for all.

        Returns:
            list: The ids.
        """
        return [
            result.item.id
            for result in self.session().rankings()
            if (retired or result.item.is_active())
            and (not category or result.item.category == category)
        ]


class TestTheListing(RankingsTestCase):
    """Test cases for the rows the sheet draws with no view control set."""

    def setUp(self):
        """Draw the plain sheet once."""
        super().setUp()
        self.body = self.sheet()

    def test_active_items_are_drawn_in_the_core_s_order(self):
        """Test that the sheet draws the fit's order, best first."""
        ids = row_ids(self.body)

        self.assertEqual(ids, self.core_order())
        self.assertEqual(ids[0], "oil")
        self.assertNotIn("red", ids)

    def test_each_row_carries_its_rank_and_figures(self):
        """Test the rank, name, category, rating, ± SE and comparison cells."""
        results = {r.item.id: r for r in self.session().rankings()}
        for item_id in row_ids(self.body):
            with self.subTest(item_id=item_id):
                result = results[item_id]
                rank, name, category, rating, se, compared = cells_of(row_of(self.body, item_id))
                self.assertEqual(rank, str(result.rank))
                self.assertEqual(name, result.item.name)
                self.assertEqual(category, result.item.category)
                self.assertEqual(rating, f"{result.elo_rating:.0f}")
                self.assertRegex(se, r"^±\d+$")
                self.assertEqual(compared, str(result.comparison_count))

    def test_the_ranks_count_active_items_from_one(self):
        """Test that the ranks drawn are 1..N with retired items left out."""
        ranks = [cells_of(row_of(self.body, i))[0] for i in row_ids(self.body)]

        self.assertEqual(ranks, [str(n) for n in range(1, len(ranks) + 1)])

    def test_the_rows_are_drawn_through_the_parts_list_macro(self):
        """Test the grid, the columns and each row's hookup to its detail."""
        self.assertIn('<table class="bom" role="grid" aria-label="Rankings">', self.body)
        for label in ("Rank", "Name", "Category", "Rating", "± SE", "Compared"):
            self.assertIn(f">{label}</th>", self.body)
        row = row_of(self.body, "oil")
        self.assertIn(f'hx-get="{RANKINGS_URL}/oil/detail"', row)
        self.assertIn('hx-target="#row-callout"', row)
        self.assertIn('hx-trigger="sheet:select"', row)
        self.assertIn('aria-controls="row-callout"', row)

    def test_the_tabs_mark_rankings_as_the_current_sheet(self):
        """Test that both copies of the tabs mark this sheet."""
        self.assertEqual(
            self.body.count(f'<a href="{RANKINGS_URL}" aria-current="page">'), 2
        )

    def test_the_title_block_names_the_project_and_its_file(self):
        """Test the Title and File cells."""
        self.assertIn("Linear switches, winter shortlist</h1>", self.body)
        self.assertIn(f'<span class="tb-file-text">{PROJECT}</span>', self.body)

    def test_the_keys_block_lists_the_sheet_s_keys(self):
        """Test that the keys block lists the mockup's five verbs."""
        for _, verb in RANKING_KEYS:
            self.assertIn(f"</span> {verb}</li>", self.body)

    def test_every_control_declares_the_key_it_answers_to(self):
        """Test C on the category, H on the retired toggle and X on Export."""
        self.assertIn('data-sheet-key="C"', element(self.body, r'<select class="input" id="category"'))
        self.assertIn('data-sheet-key="H"', element(self.body, r'<button type="submit" id="toggle-retired"'))
        export = re.search(r'<form[^>]*id="export-cell".*?</form>', self.body, re.S).group(0)
        self.assertIn(f'action="{EXPORT_URL}"', export)
        self.assertIn('data-sheet-key="X"', export)

    def test_the_summary_counts_what_is_drawn(self):
        """Test the active count shown and every retired item counted."""
        summary = re.search(r'id="tb-summary"[^>]*>(.*?)</p>', self.body, re.S).group(1)
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", summary))).strip()

        self.assertTrue(text.startswith("6 active shown · 2 retired hidden."), text)

    def test_the_boot_script_is_bound_on_window(self):
        """Test the rule a boot script that selects a row must keep."""
        self.assertIn('window.addEventListener("DOMContentLoaded"', self.body)
        self.assertNotIn('document.addEventListener("DOMContentLoaded"', self.body)


class TestShowRetired(RankingsTestCase):
    """Test cases for retired=1."""

    def test_retired_items_sit_among_the_others_by_rating(self):
        """Test that retired rows join the core's order rather than trailing it."""
        body = self.sheet("retired=1")

        self.assertEqual(row_ids(body), self.core_order(retired=True))

    def test_a_retired_row_has_no_rank_and_says_retired_in_words(self):
        """Test the dimmed row, the tag and the hidden words for the empty rank."""
        row = row_of(self.sheet("retired=1"), "red")

        self.assertIn("is-retired", row)
        self.assertIn(f'<span class="tag">{TAG_RETIRED}</span>', row)
        self.assertEqual(cells_of(row)[0], "No rank")

    def test_the_toggle_says_which_way_it_is_and_offers_the_other(self):
        """Test the toggle's pressed state and the value it would send."""
        plain = re.search(r'<form[^>]*id="retired-cell".*?</form>', self.sheet(), re.S).group(0)
        shown = re.search(
            r'<form[^>]*id="retired-cell".*?</form>', self.sheet("retired=1"), re.S
        ).group(0)

        self.assertIn('aria-pressed="false"', plain)
        self.assertIn('name="retired" value="1"', plain)
        self.assertIn('aria-pressed="true"', shown)
        self.assertNotIn('name="retired"', shown)

    def test_any_other_value_hides_them(self):
        """Test that a mistyped value draws the sheet with retired items hidden."""
        self.assertNotIn("red", row_ids(self.sheet("retired=yes")))


class TestTheCategory(RankingsTestCase):
    """Test cases for category=."""

    def test_a_category_keeps_only_its_items_in_rank_order(self):
        """Test the Tactile rows, in the core's order."""
        body = self.sheet("category=Tactile")

        self.assertEqual(row_ids(body), self.core_order(category="Tactile"))
        self.assertEqual(set(row_ids(body)), {"brown", "boba"})

    def test_ranks_stay_the_whole_project_s(self):
        """Test that a narrowed sheet keeps each item's overall rank."""
        results = {r.item.id: r for r in self.session().rankings()}
        body = self.sheet("category=Tactile")

        self.assertEqual(cells_of(row_of(body, "boba"))[0], str(results["boba"].rank))

    def test_the_options_are_every_category_the_project_has(self):
        """Test the options, All categories first, the chosen one selected."""
        body = self.sheet("category=Tactile")
        select = re.search(r'<select class="input" id="category".*?</select>', body, re.S).group(0)

        self.assertEqual(
            re.findall(r'<option value="([^"]*)"', select), ["", "Linear", "Silent", "Tactile"]
        )
        self.assertIn('<option value="Tactile" selected>', select)

    def test_a_category_the_project_does_not_have_reads_as_none(self):
        """Test that a stale address draws every row."""
        self.assertEqual(row_ids(self.sheet("category=Clicky")), self.core_order())

    def test_a_category_with_nothing_active_draws_the_empty_state(self):
        """Test the empty state, with no table, and its rows back with H."""
        self.write(
            PROJECT,
            project_data(items=ITEMS + [item("jade", "Kailh Box Jade", category="Clicky", retired=True)]),
        )

        body = self.sheet("category=Clicky")
        self.assertNotIn("<table", field_of(body))
        self.assertIn('class="bom-empty"', field_of(body))
        self.assertEqual(row_ids(self.sheet("category=Clicky&retired=1")), ["jade"])

    def test_the_category_swaps_only_the_drawing_area(self):
        """Test the htmx attributes and the cells carried out of band."""
        select = element(self.sheet(), r'<select class="input" id="category"')

        self.assertIn(f'hx-get="{RANKINGS_URL}"', select)
        self.assertIn('hx-select="#field"', select)
        self.assertIn('hx-target="#field"', select)
        self.assertIn('hx-select-oob="#retired-cell,#export-cell,#tb-summary"', select)
        self.assertIn('hx-replace-url="true"', select)

    def test_the_retired_toggle_and_export_keep_the_category(self):
        """Test that the two cells the swap carries hold the category."""
        body = self.sheet("category=Tactile&retired=1")
        for cell in ("retired-cell", "export-cell"):
            with self.subTest(cell=cell):
                form = re.search(rf'<form[^>]*id="{cell}".*?</form>', body, re.S).group(0)
                self.assertIn('name="category" value="Tactile"', form)
        export = re.search(r'<form[^>]*id="export-cell".*?</form>', body, re.S).group(0)
        self.assertIn('name="retired" value="1"', export)


class TestTheEmptyStates(RankingsTestCase):
    """Test cases for projects with nothing to rank, or no votes yet."""

    def test_fewer_than_two_active_items_offers_the_items_sheet(self):
        """Test the empty state, with no table and a way to Items."""
        self.write(PROJECT, project_data(items=ITEMS[:1] + ITEMS[5:7], votes=[]))

        field = field_of(self.sheet("retired=1"))
        self.assertNotIn("<table", field)
        self.assertIn(f'href="/projects/{PROJECT}/items"', field)

    def test_a_project_with_no_items_draws_the_empty_state(self):
        """Test a project with nothing in it at all."""
        self.write(PROJECT, project_data(items=[], votes=[]))

        self.assertNotIn("<table", field_of(self.sheet()))

    def test_no_votes_draws_every_item_by_name_with_no_figures(self):
        """Test the arbitrary order the mockup draws as names, with dashes."""
        self.write(PROJECT, project_data(votes=[]))

        body = self.sheet()
        names = {entry["id"]: entry["name"] for entry in ITEMS}
        ids = row_ids(body)
        self.assertEqual(ids, sorted(ids, key=lambda i: names[i].casefold()))
        rank, _, _, rating, se, _ = cells_of(row_of(body, "oil"))
        self.assertEqual((rank, rating, se), ("No rank", "–", "–"))


class TestArrivingSelected(RankingsTestCase):
    """Test cases for selected=, the row a page arrives on with its detail."""

    def test_the_page_asks_the_engine_to_select_the_row_with_its_detail(self):
        """Test the boot script opens the detail and selects the row."""
        body = self.sheet("selected=oil")

        self.assertIn('detailOpen = true;\n      sheet.select("oil");', body)

    def test_a_row_the_view_does_not_draw_selects_nothing(self):
        """Test that a retired item hidden from the view is not selected."""
        self.assertNotIn('sheet.select("red")', self.sheet("selected=red"))

    def test_the_id_is_never_written_as_markup(self):
        """Test that a hostile id cannot close the script it would be written into."""
        body = self.sheet("selected=%3C/script%3E%3Cb%3E")

        self.assertNotIn("</script><b>", body)


class TestTheDetail(RankingsTestCase):
    """Test cases for a row's callout: its figures beside its record."""

    def test_the_detail_is_one_popover_named_by_rank_and_name(self):
        """Test the fragment's shape and its accessible name."""
        rank = next(r.rank for r in self.session().rankings() if r.item.id == "oil")
        body = self.detail("oil")

        self.assertTrue(body.lstrip().startswith('<div class="bom-callout strip'))
        self.assertIn(f'aria-label="#{rank} Gateron Oil King"', body)
        self.assertIn('class="strip-detail"', body)
        self.assertIn("Deep, muted.", body)
        self.assertNotIn("data-sheet-key", body)

    def test_the_figures_are_the_core_s(self):
        """Test strength, log-strength, SE and the comparison count."""
        result = next(r for r in self.session().rankings() if r.item.id == "cream")
        body = self.detail("cream")

        for figure in (
            f"{result.strength:.3f}",
            f"{result.log_strength:.3f}",
            f"{result.log_strength_se:.3f}",
            f"{result.comparison_count} times",
        ):
            self.assertIn(f"<dd>{figure}</dd>", body)

    def test_the_record_has_a_line_per_opponent_most_met_first(self):
        """Test the merged wins and losses, ordered by total weight."""
        record = record_of(self.detail("cream"))

        # Cream beat Alpaca 2 and Boba 2, Brown 1, and split with Oil King
        # (lost 3, won 1); with no decay the brackets repeat the raw figure.
        self.assertEqual(record[0], ("Gateron Oil King", "1 (1.0)", "3 (3.0)"))
        self.assertEqual(
            sorted(record[1:3]),
            [("Alpaca V2", "2 (2.0)", "0"), ("Gazzew Boba U4T", "2 (2.0)", "0")],
        )
        self.assertEqual(record[3], ("Cherry MX Brown", "1 (1.0)", "0"))

    def test_the_decayed_weight_is_drawn_beside_the_raw_one(self):
        """Test "2 (1.0)" for a weight-2 vote one half-life old."""
        self.write(
            PROJECT,
            project_data(
                votes=VOTES + [vote(99, "quiet", "boba", 2, days_ago=30)], half_life=30
            ),
        )

        record = dict((name, (won, lost)) for name, won, lost in record_of(self.detail("quiet")))
        self.assertEqual(record["Gazzew Boba U4T"], ("2 (1.0)", "0"))
        self.assertIn("half-life 30 days", self.detail("quiet"))

    def test_a_long_record_is_cut_short_and_counted(self):
        """Test the first seven opponents and the count of the rest."""
        crowd = [item(f"x{n}", f"Extra {n}") for n in range(RECORD_SHOWN + 2)]
        votes = [vote(100 + n, "oil", f"x{n}", 1) for n in range(RECORD_SHOWN + 2)]
        self.write(PROJECT, project_data(items=ITEMS + crowd, votes=VOTES + votes))

        body = self.detail("oil")
        self.assertEqual(len(record_of(body)), RECORD_SHOWN)
        opponents = {"oil": 0}
        for winner, loser, _ in BEATS:
            if "oil" in (winner, loser):
                opponents[loser if winner == "oil" else winner] = 1
        more = len(opponents) - 1 + RECORD_SHOWN + 2 - RECORD_SHOWN
        self.assertIn(f"and {more} more opponents", body)

    def test_an_item_nobody_voted_on_says_so(self):
        """Test the detail of an item with no votes."""
        body = self.detail("quiet")

        self.assertEqual(record_of(body), [])
        self.assertIn("No votes involve this item yet.", body)

    def test_a_retired_item_s_detail_has_no_rank(self):
        """Test that the detail names a retired item without a number."""
        self.assertIn('aria-label="Cherry MX Red"', self.detail("red"))

    def test_a_project_with_no_votes_says_none_yet(self):
        """Test the detail's figures before any vote."""
        self.write(PROJECT, project_data(votes=[]))

        body = self.detail("oil")
        self.assertIn('aria-label="Gateron Oil King"', body)
        self.assertIn("<dd>none yet</dd>", body)
        self.assertNotIn("Strength", body)

    def test_an_item_that_is_not_there_is_not_found(self):
        """Test the 404 the engine answers by reloading the page."""
        response = self.client.get(f"{RANKINGS_URL}/nope/detail", headers={"HX-Request": "true"})

        self.assertEqual(response.status_code, 404)

    def test_a_project_too_small_to_rank_has_no_detail(self):
        """Test the 404 when there is no ranking to detail."""
        self.write(PROJECT, project_data(items=ITEMS[:1] + ITEMS[5:6], votes=[]))

        response = self.client.get(f"{RANKINGS_URL}/oil/detail")
        self.assertEqual(response.status_code, 404)


class TestTheExport(RankingsTestCase):
    """Test cases for the CSV the X key downloads."""

    def export(self, query: str = ""):
        """
        Download the export for one view.

        Args:
            query: The query string, without its "?".

        Returns:
            Response: The response, after asserting it is a CSV file.
        """
        response = self.client.get(f"{EXPORT_URL}?{query}" if query else EXPORT_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/csv; charset=utf-8")
        return response

    def test_it_downloads_as_a_file_named_after_the_project(self):
        """Test the attachment and its name."""
        disposition = self.export().headers["content-disposition"]

        self.assertTrue(disposition.startswith("attachment;"))
        self.assertIn('filename="Switches rankings.csv"', disposition)

    def test_a_name_outside_ascii_keeps_its_exact_spelling(self):
        """Test the RFC 5987 name beside a safe fallback."""
        self.write("Clé 5 #1.pairrank", project_data())

        disposition = self.client.get(
            f"/projects/{quote('Clé 5 #1.pairrank')}/rankings/export"
        ).headers["content-disposition"]
        self.assertIn('filename="Cl_ 5 #1 rankings.csv"', disposition)
        exact = re.search(r"filename\*=UTF-8''(\S+)", disposition).group(1)
        self.assertEqual(unquote(exact), "Clé 5 #1 rankings.csv")

    def test_the_columns_are_the_desktop_export_s(self):
        """Test the header row."""
        rows = list(csv.reader(io.StringIO(self.export().text)))

        self.assertEqual(rows[0], EXPORT_HEADER)

    def test_the_export_follows_the_view(self):
        """Test the rows for each view, in the core's order."""
        for query, retired, category in (
            ("", False, ""),
            ("retired=1", True, ""),
            ("category=Tactile", False, "Tactile"),
            ("category=Tactile&retired=1", True, "Tactile"),
            ("category=Clicky", False, ""),
        ):
            with self.subTest(query=query):
                rows = list(csv.reader(io.StringIO(self.export(query).text)))
                names = {entry["id"]: entry["name"] for entry in ITEMS}
                self.assertEqual(
                    [row[1] for row in rows[1:]],
                    [names[i] for i in self.core_order(retired=retired, category=category)],
                )

    def test_a_project_with_nothing_to_rank_exports_the_header(self):
        """Test the header alone rather than an error."""
        self.write(PROJECT, project_data(items=ITEMS[:1], votes=[]))

        self.assertEqual(list(csv.reader(io.StringIO(self.export().text))), [EXPORT_HEADER])

    def test_the_file_is_the_core_s_rows_written_by_csv_writer(self):
        """Test the bytes against the session's own export rows."""
        rows = self.session().export_rows(category="Linear", include_retired=True)

        self.assertEqual(
            self.export("category=Linear&retired=1").content,
            export_csv(rows).encode("utf-8"),
        )


class TestTheExportEqualsTheDesktop(RankingsTestCase):
    """The web export against the desktop's Export button, byte for byte."""

    @classmethod
    def setUpClass(cls):
        """Start an offscreen Qt application, or skip without one."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError as error:  # pragma: no cover - the desktop is a dependency
            raise unittest.SkipTest(f"PyQt6 is not available: {error}")
        cls.qt_app = QApplication.instance() or QApplication([])

    def desktop_export(self, category: str, retired: bool) -> bytes:
        """
        Press the desktop's Export button with one view set, and read the file.

        Args:
            category: The category to choose, or empty for all of them.
            retired: Whether to tick Show retired.

        Returns:
            bytes: The file the desktop wrote.
        """
        from src.ui.results import ALL_CATEGORIES, ResultsWidget

        session = self.session()
        widget = ResultsWidget()
        self.addCleanup(widget.deleteLater)
        widget.set_rankings(session.rankings(), session.project.votes)
        widget.show_retired_check.setChecked(retired)
        widget.category_filter.setCurrentText(category or ALL_CATEGORIES)
        target = self.data_dir / "desktop-export.csv"
        with mock.patch(
            "src.ui.results.QFileDialog.getSaveFileName", return_value=(str(target), "")
        ), mock.patch("src.ui.results.QMessageBox.information"), mock.patch(
            "src.ui.results.QMessageBox.critical"
        ) as failed:
            widget._on_export_clicked()
        failed.assert_not_called()
        return target.read_bytes()

    def test_every_view_exports_the_same_file(self):
        """Test each combination of category and retired items."""
        for category in ("", "Linear", "Tactile"):
            for retired in (False, True):
                with self.subTest(category=category, retired=retired):
                    query = "&".join(
                        part
                        for part in (
                            f"category={category}" if category else "",
                            "retired=1" if retired else "",
                        )
                        if part
                    )
                    web = self.client.get(f"{EXPORT_URL}?{query}").content
                    self.assertEqual(web, self.desktop_export(category, retired))


class TestProjectsThatCannotBeDrawn(RankingsTestCase):
    """Test cases for an address naming no drawable project."""

    def test_a_project_that_is_not_there_is_not_found(self):
        """Test the 404 on the sheet, the detail and the export."""
        for path in ("rankings", "rankings/oil/detail", "rankings/export"):
            with self.subTest(path=path):
                response = self.client.get(f"/projects/Nope.pairrank/{path}")
                self.assertEqual(response.status_code, 404)

    def test_a_newer_file_gets_the_newer_version_page(self):
        """Test that a file from a newer application is not called damaged."""
        self.write("Future.pairrank", project_data(format_version=CURRENT_FORMAT_VERSION + 1))

        response = self.client.get("/projects/Future.pairrank/rankings")
        self.assertEqual(response.status_code, NEWER_FORMAT_STATUS)

    def test_a_damaged_file_gets_the_damaged_page(self):
        """Test that a file that will not read lands on the damaged page."""
        self.write("Broken.pairrank", "{ not json")

        response = self.client.get("/projects/Broken.pairrank/rankings")
        self.assertEqual(response.status_code, DAMAGED_STATUS)


class TestEveryRankingsPageReadsTheFile(RankingsTestCase):
    """Test cases for the sheet, the detail and the export after an outside change."""

    def setUp(self):
        """Draw the sheet once, so the registry holds the project."""
        super().setUp()
        self.sheet()

    def add_elsewhere(self) -> None:
        """Save the project from "another program" with one more item."""
        self.write(PROJECT, project_data(items=ITEMS + [item("tealios", "Tealios V2")]))

    def cached(self) -> bool:
        """Tell whether the registry still holds the project."""
        registry = self.app.state.registry
        return registry.resolve(PROJECT) in registry._entries

    def test_the_sheet_draws_a_row_added_elsewhere(self):
        """Test the page GET."""
        self.add_elsewhere()

        self.assertIn("tealios", row_ids(self.sheet()))

    def test_the_detail_of_an_item_added_elsewhere_answers(self):
        """Test the fragment GET."""
        self.add_elsewhere()

        self.detail("tealios")

    def test_the_export_carries_a_row_added_elsewhere(self):
        """Test the export GET."""
        self.add_elsewhere()

        self.assertIn("Tealios V2", self.client.get(EXPORT_URL).text)

    def test_a_detail_after_a_delete_is_not_found_and_forgets_the_project(self):
        """Test that the stale project is neither drawn nor kept."""
        (self.data_dir / PROJECT).unlink()

        response = self.client.get(f"{RANKINGS_URL}/oil/detail", headers={"HX-Request": "true"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.cached())


class TestRankingsUnderARootPath(RankingsTestCase):
    """Test cases for the sheet behind a reverse proxy on a subpath."""

    root_path = "/rank"

    def test_every_address_the_sheet_builds_carries_the_prefix(self):
        """Test the controls, the rows, the export and the tabs under /rank."""
        body = self.sheet()
        prefixed = f"/rank{RANKINGS_URL}"

        self.assertIn(f'<form id="view" method="get" action="{prefixed}"', body)
        self.assertIn(f'hx-get="{prefixed}"', body)
        self.assertIn(f'hx-get="{prefixed}/oil/detail"', body)
        self.assertIn(f'action="{prefixed}/export"', body)
        self.assertIn(f'<a href="{prefixed}" aria-current="page">', body)
        self.assertNotIn(f'"{RANKINGS_URL}', body)


if __name__ == "__main__":
    unittest.main()
