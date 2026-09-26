"""Route tests for the Items sheet: one project's items as a parts list.

Chunk 6a's half of the screen - the table and the three controls that decide
which rows it draws. Every view of the sheet is an address, so these tests ask
for an address and look at the rows that came back: which ids, in what order,
carrying which state. The words on the page are the capture pass's business.

The fixture is the register's (``tests/test_web_projects.py``), for the reasons
§5c of the plan gives: the directory is seeded before the application is
built, the routes' own warnings are silenced without hiding them from
``assertLogs``, and a per-row assertion is made against one ``<tr>`` cut out of
the page rather than against the whole of it.
"""

import html
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.data.format_version import CURRENT_FORMAT_VERSION
from src.web.app import DAMAGED_STATUS, NEWER_FORMAT_STATUS, create_app
from src.web.routes.items import (
    FREE_LIST_SHOWN,
    ITEM_KEYS,
    TAG_NO_SLOT,
    TAG_RETIRED,
)
from tests.test_web_projects import config_for, row_of, silence


PROJECT = "Switches.pairrank"
ITEMS_URL = f"/projects/{PROJECT}/items"


def item(
    item_id: str,
    name: str,
    slot: str = "",
    category: str = "Linear",
    description: str = "",
    retired: bool = False,
) -> dict:
    """
    Build one item entry in the current format.

    Args:
        item_id: The item's id, which is also its row's ``data-id``.
        name: Its name.
        slot: Its identifier; empty for an item with no slot.
        category: Its category.
        description: Its description.
        retired: Whether it is retired, in which case it holds no slot.

    Returns:
        dict: The entry.
    """
    return {
        "id": item_id,
        "name": name,
        "description": description,
        "identifier": "" if retired else slot,
        "category": category,
        "status": "retired" if retired else "active",
    }


# A small board in the shape of the mockup's: numbered sockets out of numeric
# order in the list, and a named key position with an explicit short label.
SLOTS = ["1", "2", "10", "Apostrophe", "Enter"]
SLOT_LABELS = {"Apostrophe": "'"}

# Listed out of the order the sheet draws them in, so the order is the route's.
ITEMS = [
    item("brown", "Cherry MX Brown", category="Tactile"),
    item("jade", "Kailh Box Jade", slot="Apostrophe", category="Clicky"),
    item("blue", "Cherry MX Blue", category="Clicky", retired=True),
    item("oil", "Gateron Oil King", slot="10", description="Deep, muted."),
    item("cream", "NovelKeys Cream", slot="1"),
    item("alpaca", "Alpaca V2"),
    item("red", "Cherry MX Red", retired=True),
]


def project_data(items=ITEMS, slots=SLOTS, slot_labels=SLOT_LABELS, **extra) -> dict:
    """
    Build a project dictionary for the Items sheet.

    Args:
        items: The item entries.
        slots: The slot list.
        slot_labels: The explicit short labels.
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
        "votes": [],
        "settings": {},
        "slots": list(slots),
        "slot_labels": dict(slot_labels),
    }
    data.update(extra)
    return data


def row_ids(body: str) -> list:
    """
    List the rows a sheet drew, in order.

    Args:
        body: The rendered page.

    Returns:
        list: Each row's ``data-id``.
    """
    return re.findall(r'<tr class="bom-row[^>]*data-id="([^"]+)"', body)


def field_of(body: str) -> str:
    """
    Cut the drawing area out of a rendered sheet.

    Args:
        body: The rendered page.

    Returns:
        str: The ``.bom-field`` section, which is what the rows swap lands.
    """
    match = re.search(r'<section class="bom-field".*?</section>', body, re.S)
    return match.group(0) if match else ""


def cell_text(body: str, element_id: str) -> str:
    """
    Read one title-block paragraph the way a screen reader would.

    Args:
        body: The rendered page.
        element_id: The paragraph's id.

    Returns:
        str: Its text with the aria-hidden glyphs left out, tags stripped,
        entities decoded and whitespace collapsed - so a named slot reads as
        its full name, once.
    """
    match = re.search(rf'<p class="tb-text" id="{element_id}"[^>]*>(.*?)</p>', body, re.S)
    if not match:
        return ""
    heard = re.sub(r'<span aria-hidden="true">.*?</span>', "", match.group(1))
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", heard))).strip()


def element(body: str, pattern: str) -> str:
    """
    Cut one element's opening tag out of a page.

    Args:
        body: The rendered page.
        pattern: A regular expression matching the start of the tag.

    Returns:
        str: The whole opening tag, or an empty string.
    """
    match = re.search(pattern + r"[^>]*>", body, re.S)
    return match.group(0) if match else ""


class ItemsTestCase(unittest.TestCase):
    """Base case giving each test an application over a seeded directory."""

    root_path = ""

    def setUp(self):
        """Build an application over a data directory :meth:`seed` filled."""
        silence(self, "src.web.registry", "src.web.app", "src.web.routes.items")
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
        Draw the Items sheet at one address.

        Args:
            query: The query string, without its "?".

        Returns:
            str: The page, after asserting it was drawn.
        """
        response = self.client.get(f"{ITEMS_URL}?{query}" if query else ITEMS_URL)
        self.assertEqual(response.status_code, 200)
        return response.text


class TestTheListing(ItemsTestCase):
    """Test cases for the rows the sheet draws with no view control set."""

    def setUp(self):
        """Draw the plain sheet once."""
        super().setUp()
        self.body = self.sheet()

    def test_active_items_are_drawn_in_board_order(self):
        """
        Test that slotted items follow the slot list, then unslotted by name.

        The sheet reads down the board the way the board is laid out, so the
        slot list's order wins over the numbers' and over the items' own order
        in the file; items waiting for a slot come after, alphabetically.
        """
        self.assertEqual(row_ids(self.body), ["cream", "oil", "jade", "alpaca", "brown"])

    def test_retired_items_are_hidden_until_asked_for(self):
        """Test that a plain sheet draws no retired row."""
        self.assertNotIn("blue", row_ids(self.body))
        self.assertNotIn("is-retired", self.body)

    def test_the_rows_are_drawn_through_the_parts_list_macro(self):
        """
        Test that the table is the one the folding engine and the ARIA fix need.

        A grid, rows carrying their id and the find number in the first cell,
        and the hookup to the row's own callout, which the macro writes with
        the aria-controls that says where it lands.
        """
        self.assertIn('<table class="bom" role="grid" aria-label="Items">', self.body)
        row = row_of(self.body, "oil")
        self.assertIn('tabindex="-1"', row)
        self.assertIn('aria-selected="false"', row)
        self.assertRegex(row, r'<tr[^>]*>\s*<td class="c-find"><span class="balloon"')
        self.assertIn(f'hx-get="{ITEMS_URL}/oil/callout"', row)
        self.assertIn('hx-trigger="sheet:select"', row)
        self.assertIn('aria-controls="row-callout"', row)

    def test_a_slotted_row_carries_its_balloon_name_and_description(self):
        """Test the ordinary row: balloon, name, description, category, Active."""
        row = row_of(self.body, "oil")

        self.assertIn('<span aria-hidden="true">10</span>', row)
        self.assertIn('<span class="bom-name">Gateron Oil King</span>', row)
        self.assertIn('<span class="bom-desc">Deep, muted.</span>', row)
        self.assertIn('<span class="bom-cat">Linear</span>', row)
        self.assertIn('<span class="status">Active</span>', row)
        self.assertNotIn('class="tag"', row)

    def test_a_named_slot_shows_its_short_label_and_says_its_name(self):
        """
        Test the Short Label Rule on a balloon.

        The sheet has room for two characters, so "Apostrophe" is drawn as its
        explicit label, and the full name goes to hover and - as visually
        hidden text, not an aria-label on a bare span - to assistive
        technology.
        """
        row = row_of(self.body, "jade")

        self.assertIn('title="Slot Apostrophe"', row)
        self.assertIn('<span aria-hidden="true">&#39;</span>', row)
        self.assertIn('<span class="visually-hidden">Slot Apostrophe</span>', row)

    def test_an_item_with_no_slot_says_so_in_words(self):
        """Test the dashed balloon, and the NO SLOT tag that is its non-colour twin."""
        row = row_of(self.body, "alpaca")

        self.assertIn("balloon is-empty", row)
        self.assertIn(f'<span class="tag">{TAG_NO_SLOT}</span>', row)

    def test_the_tabs_mark_items_as_the_current_sheet(self):
        """Test that both copies of the tabs mark this sheet, and only it."""
        self.assertEqual(
            re.findall(r'<a href="([^"]+)" aria-current="page">', self.body),
            [ITEMS_URL, ITEMS_URL],
        )

    def test_the_title_block_names_the_project_and_its_file(self):
        """Test the TITLE and FILE cells."""
        self.assertIn(
            '<h1 class="tb-title-text">Linear switches, winter shortlist</h1>', self.body
        )
        self.assertIn(f'<span class="tb-file-text">{PROJECT}</span>', self.body)

    def test_the_counts_cover_the_whole_project(self):
        """Test that the Items cell counts active and retired items, drawn or not."""
        self.assertEqual(cell_text(self.body, "tb-counts"), "5 active · 2 retired")

    def test_the_keys_block_lists_the_sheet_s_keys(self):
        """Test that every key the block lists is drawn as a legend."""
        keys = re.search(r'class="tb-keylist">(.*?)</ul>', self.body, re.S).group(1)
        self.assertEqual(keys.count('class="key"'), sum(len(k) for k, _ in ITEM_KEYS))
        self.assertIn("category", keys)

    def test_every_control_declares_the_key_it_answers_to(self):
        """
        Test that the drawn legends are also wired.

        The engine presses whatever carries data-sheet-key, and focuses it when
        it is a field; aria-keyshortcuts tells assistive technology the same
        thing. A legend on a cell with neither is a key that does nothing.
        """
        for pattern, key in (
            (r'<input class="input" id="filter"', "/"),
            (r'<select class="input" id="category"', "C"),
            (r'<button type="submit" id="toggle-retired"', "H"),
            (r'<button type="submit" aria-keyshortcuts="N"', "N"),
        ):
            with self.subTest(key=key):
                tag = element(self.body, pattern)
                self.assertIn(f'data-sheet-key="{key}"', tag)
                self.assertIn(f'aria-keyshortcuts="{key}"', tag)

    def test_add_points_at_the_new_item_form(self):
        """Test that Add is a GET to this sheet's form=new address."""
        add = re.search(
            r'<form class="tb-cell tb-press span-2" id="add-cell" method="get" action="([^"]+)">\s*'
            r'<input type="hidden" name="form" value="new">',
            self.body,
        )
        self.assertIsNotNone(add)
        self.assertEqual(add.group(1), ITEMS_URL)

    def test_the_boot_script_is_bound_on_window(self):
        """
        Test rule 3 of "Writing a callout": DOMContentLoaded on window.

        Bound on document, the script races htmx's own document listener, and
        any selection it makes fires sheet:select before the row can hear it.
        """
        self.assertIn('window.addEventListener("DOMContentLoaded"', self.body)
        self.assertNotIn('document.addEventListener("DOMContentLoaded"', self.body)
        self.assertNotIn("sheet.select(\"", self.body)


class TestTheSlotsCell(ItemsTestCase):
    """Test cases for the slot summary in the title block."""

    def test_used_and_free_are_counted_against_the_slot_list(self):
        """Test the ordinary summary, free slots listed in slot-list order."""
        text = cell_text(self.sheet(), "tb-slots")

        self.assertEqual(text, "3/5 used · free: 2, Enter")

    def test_a_named_free_slot_is_listed_by_its_short_label(self):
        """
        Test the Short Label Rule in the summary.

        "Enter" has no explicit label, so it is drawn as its first two
        characters with the full name hidden beside them for assistive
        technology and on hover.
        """
        body = self.sheet()
        slots = re.search(r'id="tb-slots"[^>]*>(.*?)</p>', body, re.S).group(1)

        self.assertIn(
            '<span title="Slot Enter"><span aria-hidden="true">En</span>'
            '<span class="visually-hidden">Enter</span></span>',
            slots,
        )

    def test_a_long_free_list_is_cut_short_and_counted(self):
        """Test that nine or more free slots read as the first six and a count."""
        self.write(PROJECT, project_data(items=[], slots=[str(n) for n in range(1, 13)]))

        self.assertEqual(
            cell_text(self.sheet(), "tb-slots"),
            f"0/12 used · free: {', '.join(str(n) for n in range(1, FREE_LIST_SHOWN + 1))}"
            f" and {12 - FREE_LIST_SHOWN} more",
        )

    def test_a_full_board_says_none_are_free(self):
        """Test the slots-full state."""
        self.write(PROJECT, project_data(slots=["1", "10", "Apostrophe"]))

        self.assertEqual(cell_text(self.sheet(), "tb-slots"), "3/3 used · none free")

    def test_a_project_with_no_slot_list_says_identifiers_are_free_text(self):
        """Test the no-slot-list state, where there is nothing to count against."""
        self.write(PROJECT, project_data(slots=[], slot_labels={}))

        self.assertEqual(
            cell_text(self.sheet(), "tb-slots"),
            "No slot list. Identifiers are free text.",
        )

    def test_identifiers_with_no_slot_list_are_in_natural_order(self):
        """Test that free-text identifiers read 2 before 10, not after it."""
        self.write(
            PROJECT,
            project_data(
                items=[item("a", "A", slot="10"), item("b", "B", slot="2")],
                slots=[],
                slot_labels={},
            ),
        )

        self.assertEqual(row_ids(self.sheet()), ["b", "a"])


class TestShowRetired(ItemsTestCase):
    """Test cases for the H control: retired=1."""

    def test_retired_items_follow_the_active_ones_by_name(self):
        """Test the retired-shown order: active as before, then retired, A to Z."""
        self.assertEqual(
            row_ids(self.sheet("retired=1")),
            ["cream", "oil", "jade", "alpaca", "brown", "blue", "red"],
        )

    def test_a_retired_row_is_dimmed_and_tagged_in_words(self):
        """
        Test the retired row, and that its tag cannot be truncated away.

        Ink 3 alone is not a signal a reader with a colour-vision deficiency
        or low contrast sensitivity can rely on, so the tag is
        the signal. It sits in the Status column, outside the name that the
        ellipsis cuts.
        """
        row = row_of(self.sheet("retired=1"), "blue")

        self.assertIn("is-retired", row)
        self.assertIn("balloon is-empty", row)
        name = re.search(r'<span class="bom-name">(.*?)</span>', row).group(1)
        self.assertNotIn("tag", name)
        self.assertRegex(row, rf'<td><span class="tag">{TAG_RETIRED}</span></td>')

    def test_the_toggle_says_which_way_it_is_and_offers_the_other(self):
        """
        Test that the toggle's address is the other state, and its press says this one.

        Hidden: it asks for retired=1 and is not pressed. Shown: it asks for no
        retired at all, and is pressed.
        """
        for query, pressed, offers in (("", "false", True), ("retired=1", "true", False)):
            with self.subTest(query=query):
                cell = re.search(
                    r'<form class="tb-cell tb-press span-2" id="retired-cell".*?</form>',
                    self.sheet(query),
                    re.S,
                ).group(0)
                self.assertIn(f'aria-pressed="{pressed}"', cell)
                self.assertEqual(
                    '<input type="hidden" name="retired" value="1">' in cell, offers
                )

    def test_the_view_form_keeps_retired_shown_while_filtering(self):
        """
        Test that the filter and category carry the retired state with them.

        They submit the view form, so the form has to hold the state the
        toggle set - or typing a filter would silently hide retired items
        again. It is marked with `form` too, which is what htmx includes by.
        """
        body = self.sheet("retired=1")
        view = re.search(r'<form id="view".*?</form>', body, re.S).group(0)

        self.assertIn('<input type="hidden" name="retired" value="1" form="view">', view)
        self.assertNotIn('name="retired"', re.search(
            r'<form id="view".*?</form>', self.sheet(), re.S
        ).group(0))

    def test_any_other_value_hides_them(self):
        """Test that a mistyped address draws the sheet rather than an error."""
        self.assertNotIn("blue", row_ids(self.sheet("retired=yes")))


class TestTheFilter(ItemsTestCase):
    """Test cases for the / control: q."""

    def test_the_filter_matches_names_ignoring_case(self):
        """Test that q keeps the rows whose name contains it, in board order."""
        self.assertEqual(row_ids(self.sheet("q=cherry")), ["brown"])
        self.assertEqual(
            row_ids(self.sheet("q=CHERRY&retired=1")), ["brown", "blue", "red"]
        )

    def test_the_filter_is_drawn_back_into_its_field(self):
        """Test that the field shows the filter the address holds."""
        tag = element(self.sheet("q=oil"), r'<input class="input" id="filter"')

        self.assertIn('value="oil"', tag)
        self.assertIn('name="q"', tag)
        self.assertIn('form="view"', tag)

    def test_a_filter_matching_nothing_draws_the_empty_state_and_no_table(self):
        """
        Test the swap contract of §5c.

        The engine tells a rows swap that found nothing apart from any other
        swap by whether a table came back; an empty table would be drawn as a
        sheet of nothing, with the previous rows' selection still on it.
        """
        field = field_of(self.sheet("q=zzz"))

        self.assertIn('class="bom-empty"', field)
        self.assertNotIn("<table", field)
        self.assertNotIn("<tr", field)
        # There is something to filter, so there is nothing to add from here.
        self.assertNotIn("form=new", field)

    def test_the_retired_toggle_keeps_the_filter(self):
        """Test that pressing H does not throw the filter away."""
        cell = re.search(
            r'<form class="tb-cell tb-press span-2" id="retired-cell".*?</form>',
            self.sheet("q=cherry"),
            re.S,
        ).group(0)

        self.assertIn('<input type="hidden" name="q" value="cherry">', cell)

    def test_the_filter_swaps_only_the_drawing_area(self):
        """
        Test the htmx hookup on the filter and the category.

        Both ask for this sheet with the whole view form, pick #field out of
        the answer - the rows swap sheet.js is built for - and carry the
        retired and Add cells out of band, since their hidden fields hold the
        filter. The address in the bar is replaced, so a reload keeps the view.
        """
        body = self.sheet()
        for pattern in (r'<input class="input" id="filter"', r'<select class="input" id="category"'):
            with self.subTest(control=pattern):
                tag = element(body, pattern)
                self.assertIn(f'hx-get="{ITEMS_URL}"', tag)
                self.assertIn('hx-include="[form=view]"', tag)
                self.assertIn('hx-target="#field"', tag)
                self.assertIn('hx-select="#field"', tag)
                self.assertIn('hx-swap="outerHTML"', tag)
                self.assertIn('hx-select-oob="#retired-cell,#add-cell"', tag)
                self.assertIn('hx-replace-url="true"', tag)


class TestTheCategory(ItemsTestCase):
    """Test cases for the C control: category."""

    def test_a_category_keeps_only_its_items(self):
        """Test that category narrows the rows, and composes with the rest."""
        self.assertEqual(row_ids(self.sheet("category=Clicky")), ["jade"])
        self.assertEqual(
            row_ids(self.sheet("category=Clicky&retired=1")), ["jade", "blue"]
        )
        self.assertEqual(row_ids(self.sheet("category=Linear&q=oil")), ["oil"])

    def test_the_options_are_every_category_the_project_has(self):
        """Test the select: All categories, then each category, the chosen one selected."""
        body = self.sheet("category=Tactile")
        select = re.search(r'<select class="input" id="category".*?</select>', body, re.S).group(0)

        self.assertEqual(
            re.findall(r'<option value="([^"]*)"', select),
            ["", "Clicky", "Linear", "Tactile"],
        )
        self.assertEqual(
            re.findall(r'<option value="([^"]*)" selected', select), ["Tactile"]
        )

    def test_a_category_the_project_does_not_have_reads_as_none(self):
        """Test that a stale address draws every item rather than a sheet of nothing."""
        body = self.sheet("category=Ergonomic")

        self.assertEqual(row_ids(body), ["cream", "oil", "jade", "alpaca", "brown"])
        self.assertIn('<option value="" selected>', body)

    def test_a_category_with_nothing_active_draws_the_empty_state(self):
        """Test a category whose only items are retired, while retired items are hidden."""
        self.write(
            PROJECT,
            project_data(items=ITEMS + [item("x", "Old one", category="Silent", retired=True)]),
        )
        field = field_of(self.sheet("category=Silent"))

        self.assertIn('class="bom-empty"', field)
        self.assertNotIn("<table", field)

    def test_the_retired_toggle_keeps_the_category(self):
        """Test that pressing H does not throw the category away."""
        cell = re.search(
            r'<form class="tb-cell tb-press span-2" id="retired-cell".*?</form>',
            self.sheet("category=Clicky"),
            re.S,
        ).group(0)

        self.assertIn('<input type="hidden" name="category" value="Clicky">', cell)


class TestEmptyProjects(ItemsTestCase):
    """Test cases for a project with nothing to draw."""

    def test_a_project_with_no_items_offers_to_add_one(self):
        """Test the no-items state: the empty box, with the Add cell button in it."""
        self.write(PROJECT, project_data(items=[]))
        body = self.sheet()
        field = field_of(body)

        self.assertIn('class="bom-empty"', field)
        self.assertNotIn("<table", field)
        self.assertIn(f'href="{ITEMS_URL}?form=new"', field)
        self.assertEqual(cell_text(body, "tb-counts"), "0 active · 0 retired")

    def test_a_project_whose_items_are_all_retired_is_empty_until_h(self):
        """Test that nothing active is an empty state, and H brings the rows back."""
        self.write(PROJECT, project_data(items=[item("r", "Gone", retired=True)]))

        self.assertNotIn("<table", field_of(self.sheet()))
        self.assertEqual(row_ids(self.sheet("retired=1")), ["r"])


class TestArrivingSelected(ItemsTestCase):
    """Test cases for selected=, the row a page arrives on."""

    def test_the_page_asks_the_engine_to_select_the_row(self):
        """Test that the boot script selects the row the address names."""
        body = self.sheet("selected=oil")

        self.assertIn('sheet.select("oil")', body)

    def test_the_id_is_written_as_a_script_string_not_as_markup(self):
        """Test that a hostile id cannot close the script it is written into."""
        body = self.sheet("selected=%3C/script%3E%3Cb%3E")

        self.assertNotIn("</script><b>", body)


class TestProjectsThatCannotBeDrawn(ItemsTestCase):
    """Test cases for an address naming no drawable project."""

    def test_a_project_that_is_not_there_is_not_found(self):
        """Test the 404 for a well-formed name with no file behind it."""
        self.assertEqual(self.client.get("/projects/Nope.pairrank/items").status_code, 404)

    def test_a_name_that_is_not_a_project_file_is_refused_and_logged(self):
        """Test that an id that reaches the handler is refused by the registry."""
        with self.assertLogs("src.web.registry", "WARNING"):
            response = self.client.get("/projects/notes.txt/items")

        self.assertEqual(response.status_code, 404)

    def test_a_traversal_is_not_found(self):
        """Test that an encoded separator never reaches a file outside the directory."""
        self.assertEqual(
            self.client.get("/projects/..%2FSwitches.pairrank/items").status_code, 404
        )

    def test_a_newer_file_gets_the_newer_version_page(self):
        """Test that a file from a newer application is not called damaged."""
        self.write(
            "Future.pairrank",
            project_data(format_version=CURRENT_FORMAT_VERSION + 1),
        )

        response = self.client.get("/projects/Future.pairrank/items")
        self.assertEqual(response.status_code, NEWER_FORMAT_STATUS)

    def test_a_damaged_file_gets_the_damaged_page(self):
        """Test that a file that will not read lands on the damaged page."""
        self.write("Broken.pairrank", "{ not json")

        response = self.client.get("/projects/Broken.pairrank/items")
        self.assertEqual(response.status_code, DAMAGED_STATUS)

    def test_the_register_s_open_now_lands_on_a_sheet(self):
        """
        Test that Open ends on a drawn sheet rather than on a 404.

        DEFAULT_SHEET pointed at Items from chunk 5b until phase 7 built
        Compare, which it points at again (tests/test_web_compare.py).
        """
        response = self.client.get(f"/projects/{PROJECT}/open")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.url.path, f"/projects/{PROJECT}/compare")


class TestEveryItemsPageReadsTheFile(ItemsTestCase):
    """Test cases for pages and fragments drawn after the file changed elsewhere."""

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

    def test_the_callout_of_an_item_added_elsewhere_answers(self):
        """Test a fragment GET, which reads the file as the page does."""
        self.add_elsewhere()

        response = self.client.get(
            f"{ITEMS_URL}/tealios/callout", headers={"HX-Request": "true"}
        )

        self.assertEqual(response.status_code, 200)

    def test_a_callout_after_a_delete_is_not_found_and_forgets_the_project(self):
        """Test that the stale project is neither drawn nor kept."""
        (self.data_dir / PROJECT).unlink()

        response = self.client.get(f"{ITEMS_URL}/oil/callout", headers={"HX-Request": "true"})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.cached())

    def test_the_register_s_open_after_a_delete_is_not_found(self):
        """Test that Open does not redirect into a project whose file is gone."""
        (self.data_dir / PROJECT).unlink()

        response = self.client.get(f"/projects/{PROJECT}/open", follow_redirects=False)

        self.assertEqual(response.status_code, 404)


class TestItemsUnderARootPath(ItemsTestCase):
    """Test cases for the sheet behind a reverse proxy on a subpath."""

    root_path = "/rank"

    def test_every_address_the_sheet_builds_carries_the_prefix(self):
        """Test the controls, the view form and the tabs under /rank."""
        body = self.sheet()
        prefixed = f"/rank{ITEMS_URL}"

        self.assertIn(f'<form id="view" method="get" action="{prefixed}"', body)
        self.assertIn(f'hx-get="{prefixed}"', body)
        self.assertIn(f'<a href="{prefixed}" aria-current="page">', body)
        self.assertNotIn(f'"{ITEMS_URL}', body)


if __name__ == "__main__":
    unittest.main()
