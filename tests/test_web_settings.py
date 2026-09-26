"""Route tests for the Settings sheet: the parameter table, Save and Reset.

Every state of the sheet is an address - the saved values, a draft, the
defaults after Reset, the page a save lands on - so these tests ask for an
address or post the form and look at the file, the redirect and the table's
row states. Sentences are asserted only where they are the state: the Status
cell's lead, and the error a refused value is drawn with. Keys and the marks as
they are typed belong to ``scripts/drive_sheet.py --check settings-keys``.

The fixture is the Rankings sheet's, which is the register's (§5c of the plan).
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
from src.models.settings import Settings
from src.web.app import DAMAGED_STATUS, NEWER_FORMAT_STATUS, create_app
from src.web.routes.settings import (
    DONE_SAVED,
    ERROR_NUMBER,
    FIELDS,
    NOTE_RESET,
    NOTE_SAVED,
    NUMBER_PATTERN,
    SETTINGS_KEYS,
    format_value,
    parse_value,
)
from tests.test_web_items import element, item
from tests.test_web_projects import RegisterTestCase, config_for, silence
from tests.test_web_rankings import project_data


PROJECT = "Switches.pairrank"
SETTINGS_URL = f"/projects/{PROJECT}/settings"

# The mockup's saved state: two values off their defaults.
SAVED = {"weight_uncompared": 3.0, "decay_timescale_days": 45.0}

SLOTS = ["1", "2", "3", "Apostrophe"]

BY_KEY = {field.key: field for field in FIELDS}


def settings_data(settings: dict = SAVED, **extra) -> dict:
    """
    Build the project every test here draws.

    Args:
        settings: The file's settings.
        **extra: Top-level keys to override.

    Returns:
        dict: The project data.
    """
    items = [item("oil", "Gateron Oil King", slot="1"), item("cream", "NovelKeys Cream")]
    data = project_data(items=items, votes=[], slots=list(SLOTS))
    data["settings"] = dict(settings)
    data.update(extra)
    return data


def row_of(body: str, key: str) -> str:
    """
    Cut one parameter's row out of the table.

    Args:
        body: The page.
        key: The setting's name.

    Returns:
        str: The ``<tr>``, or an empty string.
    """
    match = re.search(rf'<tr id="row-{key}".*?</tr>', body, re.S)
    return match.group(0) if match else ""


def row_state(body: str, key: str) -> set:
    """
    Read a row's state classes.

    Args:
        body: The page.
        key: The setting's name.

    Returns:
        set: ``is-changed`` and ``is-error``, those it carries.
    """
    tag = element(body, rf'<tr id="row-{key}"')
    match = re.search(r'class="([^"]*)"', tag)
    return set(match.group(1).split()) if match else set()


def value_of(body: str, key: str):
    """
    Read what one field's control holds.

    Args:
        body: The page.
        key: The setting's name.

    Returns:
        The input's text, or whether a switch is checked.
    """
    tag = element(body, rf'<input[^>]*id="f-{key}"')
    if 'type="checkbox"' in tag:
        return " checked" in tag
    return html.unescape(re.search(r'value="([^"]*)"', tag).group(1))


def error_of(body: str, key: str) -> str:
    """
    Read the error drawn under one field.

    Args:
        body: The page.
        key: The setting's name.

    Returns:
        str: The sentence, or an empty string.
    """
    match = re.search(rf'<p class="spec-error" id="e-{key}"[^>]*>(.*?)</p>', body, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip() if match else ""


def status_of(body: str) -> str:
    """
    Read the Status cell as text.

    Args:
        body: The page.

    Returns:
        str: The cell's sentence, whitespace collapsed.
    """
    match = re.search(r'<p class="tb-text" id="status"[^>]*>(.*?)</p>', body, re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))).strip()


def tile_input(body: str, slot: str) -> str:
    """
    Cut one slot tile's label input out of the board.

    Args:
        body: The page.
        slot: The slot's name (no characters HTML escapes).

    Returns:
        str: The ``<input>`` tag, or an empty string.
    """
    return element(body, rf'<input class="slot-label" name="label:{re.escape(slot)}"')


def tile_state(body: str, slot: str) -> set:
    """
    Read a tile's state classes.

    Args:
        body: The page.
        slot: The slot's name.

    Returns:
        set: The balloon's classes.
    """
    match = re.search(
        rf'<li class="([^"]*)"[^>]*>\s*<input class="slot-label" name="label:{re.escape(slot)}"', body
    )
    return set(match.group(1).split()) if match else set()


def tile_names(body: str) -> list:
    """
    List the board's tiles in order.

    Args:
        body: The page.

    Returns:
        list: The slot name of each tile.
    """
    return [html.unescape(name) for name in re.findall(r'<input class="slot-label" name="label:([^"]*)"', body)]


def warning_of(body: str) -> str:
    """
    Read the slot warning as text.

    Args:
        body: The page.

    Returns:
        str: The warning, whitespace collapsed; empty when it is hidden.
    """
    if "hidden" in element(body, r'<div class="slot-warning"'):
        return ""
    match = re.search(r'<p id="slot-warning-text"[^>]*>(.*?)</p>', body, re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))).strip()


def valid_form(**changes) -> dict:
    """
    Build the form a browser posts for the saved settings, with changes.

    Args:
        **changes: Field values to post instead, as text; a switch is on
            when its value is anything, and left out when it is None.

    Returns:
        dict: The form.
    """
    saved = Settings.from_dict(SAVED)
    form = {}
    for field in FIELDS:
        value = getattr(saved, field.key)
        if field.kind == "switch":
            if value:
                form[field.key] = "on"
        else:
            form[field.key] = format_value(field, value)
    for key, value in changes.items():
        if value is None:
            form.pop(key, None)
        else:
            form[key] = value
    return form


class SettingsTestCase(RegisterTestCase):
    """Base case giving each test an application over a seeded directory."""

    root_path = ""

    def setUp(self):
        """Build an application over a data directory :meth:`seed` filled."""
        silence(self, "src.web.registry", "src.web.app", "src.web.routes.settings")
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
        self.write(PROJECT, settings_data())

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
        Draw the Settings sheet at one address.

        Args:
            query: The query string, without its "?".

        Returns:
            str: The page, after asserting it was drawn.
        """
        response = self.client.get(f"{SETTINGS_URL}?{query}" if query else SETTINGS_URL)
        self.assertEqual(response.status_code, 200)
        return response.text

    def save(self, form: dict):
        """
        Post the form without following the redirect.

        Args:
            form: The form.

        Returns:
            The 303.
        """
        response = self.client.post(SETTINGS_URL, data=form, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        return response

    def stored(self) -> dict:
        """
        Read the settings from the file.

        Returns:
            dict: The file's settings object.
        """
        return json.loads((self.data_dir / PROJECT).read_text(encoding="utf-8"))["settings"]

    def stored_slots(self) -> list:
        """
        Read the slot list from the file.

        Returns:
            list: The file's slots.
        """
        return json.loads((self.data_dir / PROJECT).read_text(encoding="utf-8"))["slots"]


class TestTheSavedSheet(SettingsTestCase):
    """Test cases for the sheet drawn from the file: the mockup's Saved state."""

    def setUp(self):
        """Draw the plain sheet once."""
        super().setUp()
        self.body = self.sheet()

    def test_every_field_holds_its_saved_value(self):
        """Test each control against the file, written as the mockup writes it."""
        expected = {
            "weight_uncertainty": "1.0",
            "weight_connectivity": "1.0",
            "weight_freshness": "0.5",
            "weight_uncompared": "3.0",
            "decay_timescale_days": "45",
            "top_tier_mode": False,
            "top_tier_count": "10",
            "top_tier_weight": "2.0",
            "cross_category_rate": "0.10",
            "blinded_comparison_mode": False,
        }
        self.assertEqual({key: value_of(self.body, key) for key in expected}, expected)

    def test_rows_are_in_the_mockups_groups_and_order(self):
        """Test the five groups and the ten rows under them."""
        groups = re.findall(r'<th colspan="4" scope="rowgroup">([^<]*)</th>', self.body)
        self.assertEqual(
            groups,
            ["Pair selection weights", "Vote decay", "Top-tier focus",
             "Category comparisons", "Comparison mode"],
        )
        rows = re.findall(r'<tr id="row-([a-z_]+)"', self.body)
        self.assertEqual(rows, [field.key for field in FIELDS])
        self.assertEqual(set(rows), set(Settings().to_dict()))

    def test_nothing_is_marked_changed_or_in_error(self):
        """Test that the saved values draw no marks and no errors."""
        for field in FIELDS:
            with self.subTest(field=field.key):
                self.assertEqual(row_state(self.body, field.key), set())
                self.assertEqual(error_of(self.body, field.key), "")
        self.assertNotIn("aria-invalid", self.body)
        self.assertNotIn("autofocus", self.body)

    def test_the_status_says_nothing_is_unsaved(self):
        """Test the cell, with the file's stored modified time."""
        self.assertEqual(status_of(self.body), "No unsaved changes. Last saved 2026-09-16 21:04.")

    def test_default_and_range_columns(self):
        """Test the two reference columns for one field of each kind."""
        cells = {
            key: re.findall(r'<td class="spec-(?:default|range)[^"]*">([^<]*)</td>', row_of(self.body, key))
            for key in ("weight_freshness", "decay_timescale_days", "top_tier_count",
                        "cross_category_rate", "top_tier_mode")
        }
        self.assertEqual(
            cells,
            {
                "weight_freshness": ["0.5", "≥ 0"],
                "decay_timescale_days": ["30", "≥ 0 days"],
                "top_tier_count": ["10", "≥ 1 items"],
                "cross_category_rate": ["0.10", "0–1"],
                "top_tier_mode": ["Off", "on / off"],
            },
        )

    def test_every_input_carries_its_saved_value_and_default(self):
        """Test the values settings.js computes the marks and Reset from."""
        tag = element(self.body, r'<input[^>]*id="f-weight_uncompared"')
        self.assertIn('data-saved="3.0"', tag)
        self.assertIn('data-default="2.0"', tag)
        self.assertIn('data-error-range="Must be 0 or more."', tag)
        switch = element(self.body, r'<input[^>]*id="f-blinded_comparison_mode"')
        self.assertIn('data-saved=""', switch)
        self.assertIn('data-default=""', switch)

    def test_the_form_posts_to_the_sheet_and_every_field_joins_it(self):
        """Test the empty form element and the form= on each field and button."""
        self.assertIn(f'<form id="settings" method="post" action="{SETTINGS_URL}"', self.body)
        for field in FIELDS:
            with self.subTest(field=field.key):
                self.assertIn('form="settings"', element(self.body, rf'<input[^>]*id="f-{field.key}"'))
        save = element(self.body, r'<button type="submit" id="save"')
        self.assertIn('form="settings"', save)
        self.assertIn('aria-keyshortcuts="Control+S"', save)
        self.assertNotIn("disabled", save)
        reset = element(self.body, r'<button type="submit" id="reset"')
        self.assertIn('formmethod="get"', reset)
        self.assertIn(f'formaction="{SETTINGS_URL}"', reset)
        self.assertIn('name="reset" value="1"', reset)

    def test_the_title_block(self):
        """Test the keys, the title, the file and the one sheet."""
        for legends, verb in SETTINGS_KEYS:
            with self.subTest(verb=verb):
                self.assertIn(f'<span class="key">{legends[0]}</span></span> {verb}', self.body)
        self.assertIn('<h1 class="tb-title-text">Linear switches, winter shortlist</h1>', self.body)
        self.assertIn(f'<span class="tb-file-text">{PROJECT}</span>', self.body)
        self.assertIn('<span class="num" id="sheet-no">1 of 1</span>', self.body)
        self.assertIn('style="--tb-rows: 3"', self.body)

    def test_the_slot_table_is_editable_and_joins_the_form(self):
        """Test the list, its saved line, the count and a tile per slot."""
        textarea = element(self.body, r'<textarea[^>]*id="slots"')
        self.assertNotIn("readonly", textarea)
        self.assertIn('name="slots" form="settings"', textarea)
        self.assertIn('data-saved="1, 2, 3, Apostrophe"', textarea)
        self.assertIn(">1, 2, 3, Apostrophe</textarea>", self.body)
        self.assertIn('id="slots-count">4 slots &middot; 1 in use<', self.body)
        self.assertEqual(tile_names(self.body), SLOTS)
        self.assertNotIn("is-changed", element(self.body, r'<section class="spec-slots'))

    def test_each_tile_is_a_label_input_with_the_derived_placeholder(self):
        """Test owner answer 1's tile: empty, placeholder the first two characters."""
        tile = tile_input(self.body, "Apostrophe")
        self.assertIn('placeholder="Ap"', tile)
        self.assertIn('value=""', tile)
        self.assertIn('form="settings"', tile)
        self.assertIn('maxlength="2"', tile)
        self.assertIn("is-used", tile_state(self.body, "1"))
        self.assertNotIn("is-used", tile_state(self.body, "2"))
        self.assertIn("hidden", element(self.body, r'<div class="slot-warning"'))

    def test_the_page_loads_its_script_and_not_the_sheet_engine(self):
        """Test that settings.js is loaded and sheet.js (no parts list) is not."""
        self.assertIn("/static/js/settings.js", self.body)
        self.assertNotIn("sheet.js", self.body)
        self.assertIn('class="frame-inner spec-sheet"', self.body)
        self.assertIn(f'<a href="{SETTINGS_URL}" aria-current="page">', self.body)


class TestDrafts(SettingsTestCase):
    """Test cases for a draft drawn from its address: marks and errors."""

    def test_changed_values_are_marked(self):
        """Test the mockup's Unsaved changes state."""
        body = self.sheet(
            "draft=1&weight_freshness=0.75&top_tier_mode=1&blinded_comparison_mode=1"
        )
        changed = {field.key for field in FIELDS if "is-changed" in row_state(body, field.key)}
        self.assertEqual(changed, {"weight_freshness", "top_tier_mode", "blinded_comparison_mode"})
        self.assertEqual(value_of(body, "weight_freshness"), "0.75")
        self.assertTrue(value_of(body, "top_tier_mode"))
        self.assertTrue(status_of(body).startswith("3 unsaved changes: Freshness, Top-tier focus, Blinded."))

    def test_a_field_left_out_holds_its_saved_value(self):
        """Test that a draft need not name every numeric field."""
        body = self.sheet("draft=1")
        self.assertEqual(value_of(body, "weight_uncompared"), "3.0")
        self.assertEqual(row_state(body, "weight_uncompared"), set())

    def test_a_switch_left_out_of_a_draft_is_off(self):
        """Test a form's semantics: an unchecked box sends nothing."""
        self.write(PROJECT, settings_data(dict(SAVED, top_tier_mode=True)))
        body = self.sheet("draft=1")
        self.assertFalse(value_of(body, "top_tier_mode"))
        self.assertEqual(row_state(body, "top_tier_mode"), {"is-changed"})

    def test_the_same_number_spelled_differently_is_not_a_change(self):
        """Test that marks compare values, not text."""
        body = self.sheet("draft=1&weight_uncompared=3&cross_category_rate=.1&decay_timescale_days=45.0")
        for key in ("weight_uncompared", "cross_category_rate", "decay_timescale_days"):
            with self.subTest(key=key):
                self.assertEqual(row_state(body, key), set())

    def test_an_invalid_value_is_drawn_with_its_error(self):
        """Test the mockup's Invalid value state."""
        body = self.sheet("draft=1&weight_freshness=0.75&cross_category_rate=1.5")
        self.assertEqual(row_state(body, "cross_category_rate"), {"is-changed", "is-error"})
        self.assertEqual(error_of(body, "cross_category_rate"), "Must be between 0 and 1.")
        tag = element(body, r'<input[^>]*id="f-cross_category_rate"')
        self.assertIn('aria-invalid="true"', tag)
        self.assertEqual(
            status_of(body),
            "Fix 1 value before saving. Cross-category rate: Must be between 0 and 1.",
        )
        self.assertIn('class="tb-cell tb-status span-6 phone-wide is-error"', body)

    def test_a_full_width_digit_is_drawn_as_no_number(self):
        """Test the draft a refused "３" lands on: the error settings.js draws (R8 F2)."""
        body = self.sheet("draft=1&top_tier_count=３")
        self.assertEqual(row_state(body, "top_tier_count"), {"is-changed", "is-error"})
        self.assertEqual(error_of(body, "top_tier_count"), ERROR_NUMBER)
        self.assertEqual(status_of(body), f"Fix 1 value before saving. Top-tier size: {ERROR_NUMBER}")

    def test_a_posted_full_width_digit_is_refused(self):
        """Test that the server does not save what the script refuses."""
        before = self.snapshot()
        path, query = self.redirect_of(self.save(valid_form(top_tier_count="３")))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(query["top_tier_count"], "３")
        self.assertEqual(query["submitted"], "1")

    def test_a_draft_merely_drawn_takes_no_focus(self):
        """Test that only a refused save moves the caret, so the page stays at the top."""
        body = self.sheet("draft=1&cross_category_rate=1.5")
        self.assertNotIn("autofocus", body)

    def test_only_the_first_invalid_field_takes_the_focus(self):
        """Test one autofocus after a refused save, on the first error in table order."""
        body = self.sheet("draft=1&submitted=1&weight_uncertainty=-1&cross_category_rate=2")
        self.assertEqual(body.count("autofocus"), 1)
        self.assertIn("autofocus", element(body, r'<input[^>]*id="f-weight_uncertainty"'))
        self.assertTrue(status_of(body).startswith("Fix 2 values before saving."))

    def test_parameters_outside_a_draft_are_ignored(self):
        """Test that field values without draft=1, or a mistyped one, draw the saved sheet."""
        for query in ("weight_freshness=9", "draft=yes&weight_freshness=9", "reset=yes"):
            with self.subTest(query=query):
                body = self.sheet(query)
                self.assertEqual(value_of(body, "weight_freshness"), "0.5")
                self.assertNotIn("is-changed", body)


class TestSave(SettingsTestCase):
    """Test cases for posting the form: what is written and where it lands."""

    def test_a_save_writes_the_values_and_lands_saved(self):
        """Test the file and the redirect."""
        response = self.save(
            valid_form(weight_freshness="0.75", top_tier_mode="on", top_tier_count=" 12 ")
        )
        path, query = self.redirect_of(response)
        self.assertEqual((path, query), (SETTINGS_URL, {"done": DONE_SAVED}))
        stored = self.stored()
        self.assertEqual(stored["weight_freshness"], 0.75)
        self.assertTrue(stored["top_tier_mode"])
        self.assertEqual(stored["top_tier_count"], 12)
        self.assertIsInstance(stored["top_tier_count"], int)
        self.assertEqual(stored["weight_uncompared"], 3.0)
        self.assertEqual(stored["decay_timescale_days"], 45.0)

    def test_the_landed_page_says_saved_with_the_save_time(self):
        """Test the note while the save is the project's last change."""
        self.save(valid_form(weight_freshness="0.75"))
        body = self.sheet(f"done={DONE_SAVED}")
        change = self.app.state.registry.open(PROJECT).last_change
        self.assertEqual(change.kind, DONE_SAVED)
        self.assertEqual(
            status_of(body),
            f"{NOTE_SAVED} No unsaved changes. Last saved {change.time:%H:%M}.",
        )
        self.assertEqual(value_of(body, "weight_freshness"), "0.75")
        self.assertNotIn("is-changed", body)

    def test_done_saved_without_that_save_says_nothing_of_it(self):
        """Test ruling C: an address alone cannot make the sheet claim a save."""
        body = self.sheet(f"done={DONE_SAVED}")
        self.assertEqual(status_of(body), "No unsaved changes. Last saved 2026-09-16 21:04.")

    def test_a_save_leaves_the_slots_alone(self):
        """Test that the read-only panel posts nothing and the slots stay."""
        self.save(valid_form(weight_freshness="0.75"))
        self.assertEqual(self.stored_slots(), SLOTS)

    def test_a_posted_slot_list_is_applied(self):
        """Test the path 8c's slot table will use: slots saved with the settings."""
        self.save(dict(valid_form(), slots="A1, A2, A1, , B1"))
        self.assertEqual(self.stored_slots(), ["A1", "A2", "B1"])

    def test_an_unchecked_switch_is_saved_off(self):
        """Test that a switch left out of the post turns it off."""
        self.write(PROJECT, settings_data(dict(SAVED, blinded_comparison_mode=True)))
        self.save(valid_form(blinded_comparison_mode=None))
        self.assertFalse(self.stored()["blinded_comparison_mode"])

    def test_a_numeric_field_left_out_keeps_its_value(self):
        """Test the lenient post: only what is sent changes."""
        self.save({"weight_freshness": "4"})
        stored = self.stored()
        self.assertEqual(stored["weight_freshness"], 4.0)
        self.assertEqual(stored["weight_uncompared"], 3.0)

    def test_zero_half_life_and_large_values_are_saved(self):
        """Test that 0 turns decay off and nothing has an upper cap."""
        self.save(
            valid_form(decay_timescale_days="0", weight_uncertainty="250",
                       top_tier_count="1000", cross_category_rate="1")
        )
        stored = self.stored()
        self.assertEqual(stored["decay_timescale_days"], 0.0)
        self.assertEqual(stored["weight_uncertainty"], 250.0)
        self.assertEqual(stored["top_tier_count"], 1000)
        self.assertEqual(stored["cross_category_rate"], 1.0)

    def test_a_save_changes_the_rankings_half_life(self):
        """Test that the Rankings detail reads the new half-life at once."""
        self.save(valid_form(decay_timescale_days="7"))
        response = self.client.get(f"/projects/{PROJECT}/rankings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.app.state.registry.open(PROJECT).session.project.settings.decay_timescale_days, 7.0)

    def test_a_save_reads_the_file_first(self):
        """Test that a save over a file changed elsewhere keeps the other change."""
        self.sheet()
        data = settings_data()
        data["name"] = "Renamed elsewhere"
        self.write(PROJECT, data)
        self.save(valid_form(weight_freshness="0.75"))
        saved = json.loads((self.data_dir / PROJECT).read_text(encoding="utf-8"))
        self.assertEqual(saved["name"], "Renamed elsewhere")
        self.assertEqual(saved["settings"]["weight_freshness"], 0.75)


class TestSaveRefusals(SettingsTestCase):
    """Test cases for every value the model refuses: nothing written, the draft drawn."""

    REFUSED = (
        ("weight_uncertainty", "-1", "Must be 0 or more."),
        ("weight_connectivity", "-0.5", "Must be 0 or more."),
        ("weight_freshness", "", "Enter a value of 0 or more."),
        ("weight_uncompared", "lots", "Enter a number."),
        ("decay_timescale_days", "-30", "Must be 0 or more."),
        ("top_tier_count", "0", "Must be 1 or more."),
        ("top_tier_count", "2.5", "Enter a whole number."),
        ("top_tier_count", "", "Enter a value of 1 or more."),
        ("top_tier_weight", "nan", "Enter a number."),
        ("top_tier_weight", "inf", "Enter a number."),
        ("top_tier_weight", "1e999", "Enter a number."),
        ("top_tier_weight", "1_000", "Enter a number."),
        ("cross_category_rate", "1.5", "Must be between 0 and 1."),
        ("cross_category_rate", "-0.1", "Must be between 0 and 1."),
        ("cross_category_rate", " ", "Enter a value from 0 to 1."),
    )

    def test_each_refusal_writes_nothing_and_lands_on_the_draft(self):
        """Test the file, the redirect's query and the error it draws."""
        for key, raw, sentence in self.REFUSED:
            with self.subTest(key=key, raw=raw):
                before = self.snapshot()
                changes = {"weight_freshness": "0.75", "top_tier_mode": "on", key: raw}
                form = valid_form(**changes)

                path, query = self.redirect_of(self.save(form))

                self.assertEqual(self.snapshot(), before)
                self.assertEqual(path, SETTINGS_URL)
                self.assertEqual(query["draft"], "1")
                self.assertEqual(query["submitted"], "1")
                # parse_qs drops an empty value, which reads back as empty.
                self.assertEqual(query.get(key, ""), raw)
                self.assertEqual(query["top_tier_mode"], "1")
                self.assertNotIn("blinded_comparison_mode", query)
                if key != "weight_freshness":
                    self.assertEqual(query["weight_freshness"], "0.75")

                body = self.client.get(self.save(form).headers["location"]).text
                self.assertEqual(error_of(body, key), sentence)
                self.assertIn("is-error", row_state(body, key))
                self.assertTrue(value_of(body, "top_tier_mode"))

    def test_a_refusal_records_no_change(self):
        """Test that a refused save leaves the registry's last change alone."""
        self.save(valid_form(cross_category_rate="3"))
        self.assertIsNone(self.app.state.registry.open(PROJECT).last_change)

    def test_a_refused_post_carries_the_slot_text_back(self):
        """Test that a posted slot list survives a refusal in the draft's address."""
        _, query = self.redirect_of(self.save(dict(valid_form(top_tier_count="0"), slots="A, B")))
        self.assertEqual(query["slots"], "A, B")
        self.assertEqual(self.stored_slots(), SLOTS)


class TestSlotDrafts(SettingsTestCase):
    """Test cases for the slot table drawn from a draft: board, marks and warnings."""

    def test_a_drafted_list_draws_its_board_and_marks_the_table(self):
        """Test that a draft's slots are drawn, counted and named in the Status."""
        body = self.sheet("draft=1&slots=1, 2, Esc")
        self.assertIn(">1, 2, Esc</textarea>", body)
        self.assertEqual(tile_names(body), ["1", "2", "Esc"])
        self.assertIn('id="slots-count">3 slots &middot; 1 in use<', body)
        self.assertIn("is-changed", element(body, r'<section class="spec-slots'))
        self.assertEqual(
            status_of(body), "1 unsaved change: Slots. Changed values are marked with a triangle."
        )

    def test_slots_outside_a_draft_are_ignored(self):
        """Test that the saved list is drawn without draft=1."""
        self.assertEqual(tile_names(self.sheet("slots=A, B")), SLOTS)

    def test_the_mockups_duplicate_slots_state(self):
        """Test dupslots: each repeat marked on its tile and warned of once."""
        body = self.sheet("draft=1&slots=1, 2, 3, Apostrophe, 3, 1, Esc")
        self.assertEqual(tile_names(body), ["1", "2", "3", "Apostrophe", "Esc"])
        self.assertIn("is-dup", tile_state(body, "1"))
        self.assertIn("is-dup", tile_state(body, "3"))
        self.assertNotIn("is-dup", tile_state(body, "2"))
        self.assertEqual(warning_of(body), "Slots 3, 1 are listed twice. Duplicates are dropped when you save.")
        self.assertNotIn("is-error", element(body, r'<div class="tb-cell tb-status'))

    def test_derived_labels_colliding_are_flagged_not_refused(self):
        """Test the collision warning on the tiles, and that nothing is in error."""
        body = self.sheet("draft=1&slots=Apex, Apostrophe, 7")
        self.assertIn("is-clash", tile_state(body, "Apex"))
        self.assertIn("is-clash", tile_state(body, "Apostrophe"))
        self.assertNotIn("is-clash", tile_state(body, "7"))
        self.assertEqual(
            warning_of(body),
            "Slots Apex and Apostrophe both show Ap. Type a short label on one of their tiles.",
        )
        self.assertNotIn("is-error", body)

    def test_a_label_drafted_on_a_tile_is_drawn_and_marked(self):
        """Test a label in the draft's address, and that it resolves the collision."""
        body = self.sheet("draft=1&slots=Apex, Apostrophe&label:Apostrophe='")
        self.assertIn('value="&#39;"', tile_input(body, "Apostrophe"))
        self.assertEqual(warning_of(body), "")
        self.assertNotIn("is-clash", tile_state(body, "Apex"))

    def test_a_label_change_alone_is_a_slot_change(self):
        """Test that the Status names Slots when only a label changed."""
        body = self.sheet("draft=1&label:Apostrophe=AP")
        self.assertIn("is-changed", element(body, r'<section class="spec-slots'))
        self.assertIn("Slots.", status_of(body))

    def test_the_saved_label_is_drawn_on_its_tile(self):
        """Test a saved label in its tile, with the derived label as placeholder."""
        self.write(PROJECT, settings_data(slot_labels={"Apostrophe": "'"}))
        body = self.sheet()
        tile = tile_input(body, "Apostrophe")
        self.assertIn('value="&#39;"', tile)
        self.assertIn('placeholder="Ap"', tile)
        self.assertIn("&#34;Apostrophe&#34;: &#34;&#39;&#34;", element(body, r'<ul class="slot-board"'))

    def test_a_refused_label_is_drawn_with_its_error(self):
        """Test each refusal's sentence, its tile, and the Status count."""
        cases = (
            ("draft=1&label:Apostrophe=abc", "Use at most 2 characters."),
            ("draft=1&label:Apostrophe=1", "Slot 1 already shows 1."),
            ("draft=1&label:2=x&label:Apostrophe=x", "Slot 2 already shows x."),
        )
        for query, sentence in cases:
            with self.subTest(query=query):
                body = self.sheet(query)
                self.assertIn("is-error", tile_state(body, "Apostrophe"))
                self.assertIn('aria-invalid="true"', tile_input(body, "Apostrophe"))
                self.assertIn(f"Slot Apostrophe: {sentence}", status_of(body))
                self.assertTrue(status_of(body).startswith("Fix 1 value before saving."))
                self.assertNotIn("autofocus", tile_input(body, "Apostrophe"))

    def test_a_refused_post_puts_the_caret_on_the_tile(self):
        """Test that submitted=1 focuses the first tile in error when no value is."""
        body = self.sheet("draft=1&submitted=1&label:Apostrophe=abc")
        self.assertIn("autofocus", tile_input(body, "Apostrophe"))
        body = self.sheet("draft=1&submitted=1&label:Apostrophe=abc&top_tier_count=0")
        self.assertNotIn("autofocus", tile_input(body, "Apostrophe"))
        self.assertIn("autofocus", element(body, r'<input[^>]*id="f-top_tier_count"'))

    def test_reset_keeps_a_drafted_slot_table(self):
        """Test the no-JS Reset: the form's slots and tiles come back as typed."""
        body = self.sheet("reset=1&slots=1, 2, Esc&label:Esc=X")
        self.assertIn(">1, 2, Esc</textarea>", body)
        self.assertIn('value="X"', tile_input(body, "Esc"))


class TestSlotSaves(SettingsTestCase):
    """Test cases for saving the slot list and its labels, and every refusal."""

    def stored_labels(self) -> dict:
        """
        Read the short labels from the file.

        Returns:
            dict: The file's slot_labels.
        """
        return json.loads((self.data_dir / PROJECT).read_text(encoding="utf-8")).get("slot_labels", {})

    def test_a_list_and_a_label_are_saved_together(self):
        """Test one save writing the list, a label and the settings."""
        form = dict(valid_form(weight_freshness="0.75"), slots="1, 2, Apex, Apostrophe")
        form["label:Apostrophe"] = "'"
        form["label:Apex"] = ""
        self.assertEqual(self.redirect_of(self.save(form))[1], {"done": DONE_SAVED})
        self.assertEqual(self.stored_slots(), ["1", "2", "Apex", "Apostrophe"])
        self.assertEqual(self.stored_labels(), {"Apostrophe": "'"})
        self.assertEqual(self.stored()["weight_freshness"], 0.75)

    def test_a_label_equal_to_the_derived_one_is_not_stored(self):
        """Test that typing a slot's own first two characters stores nothing."""
        self.save(dict(valid_form(), slots="1, Apostrophe", **{"label:Apostrophe": "Ap", "label:1": "1"}))
        self.assertEqual(self.stored_labels(), {})

    def test_a_label_for_a_removed_slot_is_dropped(self):
        """Test that a tile posted for a slot no longer listed stores nothing."""
        self.write(PROJECT, settings_data(slot_labels={"Apostrophe": "'"}))
        self.save(dict(valid_form(), slots="1, 2, 3", **{"label:Apostrophe": "'"}))
        self.assertEqual(self.stored_labels(), {})
        self.assertEqual(self.stored_slots(), ["1", "2", "3"])

    def test_an_emptied_tile_removes_the_label(self):
        """Test that clearing a tile goes back to the derived label."""
        self.write(PROJECT, settings_data(slot_labels={"Apostrophe": "'"}))
        self.save(dict(valid_form(), slots="1, 2, 3, Apostrophe", **{"label:Apostrophe": " "}))
        self.assertEqual(self.stored_labels(), {})

    def test_a_slot_without_a_tile_keeps_its_saved_label(self):
        """Test the no-JS post: a slot with no tile field keeps what it had."""
        self.write(PROJECT, settings_data(slot_labels={"Apostrophe": "'"}))
        self.save(dict(valid_form(), slots="1, 2, 3, Apostrophe, Esc"))
        self.assertEqual(self.stored_labels(), {"Apostrophe": "'"})
        self.assertEqual(self.stored_slots(), ["1", "2", "3", "Apostrophe", "Esc"])

    def test_a_post_without_slots_or_tiles_keeps_both(self):
        """Test the lenient post: only the settings change."""
        self.write(PROJECT, settings_data(slot_labels={"Apostrophe": "'"}))
        self.save(valid_form(weight_freshness="0.75"))
        self.assertEqual(self.stored_labels(), {"Apostrophe": "'"})
        self.assertEqual(self.stored_slots(), SLOTS)

    def test_duplicates_and_derived_collisions_are_saved(self):
        """Test that the two warnings do not block a save."""
        self.save(dict(valid_form(), slots="Apex, Apostrophe, Apex"))
        self.assertEqual(self.stored_slots(), ["Apex", "Apostrophe"])

    def test_each_label_refusal_writes_nothing_and_lands_on_the_draft(self):
        """Test the file, the redirect's query and the error each refusal draws."""
        cases = (
            ({"label:Apostrophe": "abc"}, "Use at most 2 characters."),
            ({"label:Apostrophe": "1"}, "Slot 1 already shows 1."),
            ({"label:3": "q", "label:Apostrophe": "q"}, "Slot 3 already shows q."),
            ({"label:Apostrophe": "Es"}, "Slot Esc already shows Es."),
        )
        for labels, sentence in cases:
            with self.subTest(labels=labels):
                before = self.snapshot()
                form = dict(valid_form(weight_freshness="0.75"), slots="1, 2, 3, Apostrophe, Esc", **labels)
                form["label:2"] = ""

                path, query = self.redirect_of(self.save(form))

                self.assertEqual(self.snapshot(), before)
                self.assertIsNone(self.app.state.registry.open(PROJECT).last_change)
                self.assertEqual(path, SETTINGS_URL)
                self.assertEqual(query["submitted"], "1")
                self.assertEqual(query["slots"], "1, 2, 3, Apostrophe, Esc")
                self.assertEqual(query["weight_freshness"], "0.75")
                for key, value in labels.items():
                    self.assertEqual(query[key], value)
                # An empty tile that was empty before is not carried.
                self.assertNotIn("label:2", query)

                body = self.client.get(self.save(form).headers["location"]).text
                self.assertIn(f"Slot Apostrophe: {sentence}", status_of(body))
                self.assertIn("is-error", tile_state(body, "Apostrophe"))
                self.assertIn("autofocus", tile_input(body, "Apostrophe"))

    def test_an_emptied_saved_label_travels_in_the_draft(self):
        """Test that clearing a saved label survives a refusal as an empty field."""
        self.write(PROJECT, settings_data(slot_labels={"Apostrophe": "'"}))
        form = dict(valid_form(top_tier_count="0"), slots="1, 2, 3, Apostrophe", **{"label:Apostrophe": ""})
        location = self.save(form).headers["location"]
        self.assertIn("label%3AApostrophe=&", location + "&")
        body = self.client.get(location).text
        self.assertIn('value=""', tile_input(body, "Apostrophe"))


class TestReset(SettingsTestCase):
    """Test cases for Reset: the defaults drawn, the slots untouched, nothing saved."""

    def test_reset_fills_every_default_and_saves_nothing(self):
        """Test the mockup's After reset state."""
        before = self.snapshot()
        body = self.sheet("reset=1")
        defaults = Settings()
        for field in FIELDS:
            with self.subTest(field=field.key):
                expected = getattr(defaults, field.key)
                if field.kind == "switch":
                    self.assertEqual(value_of(body, field.key), expected)
                else:
                    self.assertEqual(value_of(body, field.key), format_value(field, expected))
        self.assertEqual(self.snapshot(), before)

    def test_reset_marks_what_differs_from_the_saved_values(self):
        """Test that the marks are against the file, not the defaults."""
        body = self.sheet("reset=1")
        changed = {field.key for field in FIELDS if "is-changed" in row_state(body, field.key)}
        self.assertEqual(changed, set(SAVED))
        self.assertEqual(
            status_of(body),
            f"{NOTE_RESET} 2 unsaved changes: Uncompared, Half-life. "
            "Changed values are marked with a triangle.",
        )

    def test_reset_leaves_the_slot_list_alone(self):
        """Test the slot panel after Reset."""
        body = self.sheet("reset=1")
        self.assertIn(">1, 2, 3, Apostrophe</textarea>", body)

    def test_reset_overrides_a_draft(self):
        """Test the no-JS Reset: a GET carrying the form's values and reset=1."""
        body = self.sheet("reset=1&draft=1&weight_freshness=9&cross_category_rate=5")
        self.assertEqual(value_of(body, "weight_freshness"), "0.5")
        self.assertNotIn("is-error", body)

    def test_saving_after_reset_writes_the_defaults_and_keeps_the_slots(self):
        """Test the round trip: Reset's values posted as they are drawn."""
        body = self.sheet("reset=1")
        form = {}
        for field in FIELDS:
            value = value_of(body, field.key)
            if field.kind != "switch":
                form[field.key] = value
            elif value:
                form[field.key] = "on"
        self.save(form)
        self.assertEqual(Settings.from_dict(self.stored()), Settings())
        self.assertEqual(self.stored_slots(), SLOTS)


class TestParsing(unittest.TestCase):
    """Test cases for reading typed values and writing them back."""

    def test_every_saved_value_reads_back_as_itself(self):
        """Test that saving an untouched form cannot change a value."""
        samples = {
            "weight_freshness": [0.5, 0.1, 1 / 3, 1e-7, 12345.678],
            "decay_timescale_days": [0.0, 30.0, 7.5, 0.25],
            "cross_category_rate": [0.1, 0.125, 1 / 3, 1.0, 0.0],
            "top_tier_count": [1, 10, 250],
        }
        for key, values in samples.items():
            field = BY_KEY[key]
            for value in values:
                with self.subTest(key=key, value=value):
                    parsed, error = parse_value(field, format_value(field, value))
                    self.assertIsNone(error)
                    self.assertEqual(parsed, value)

    def test_other_scripts_digits_are_no_number(self):
        """Test that only ASCII digits make a number, as settings.js reads them (R8 F2)."""
        for key in ("weight_freshness", "top_tier_count", "cross_category_rate"):
            for raw in ("３", "٣", "२", "1٣", "0.５", "1e٣"):
                with self.subTest(key=key, raw=raw):
                    self.assertEqual(parse_value(BY_KEY[key], raw), (None, ERROR_NUMBER))

    def test_the_number_pattern_holds_no_unicode_class(self):
        """Test that the pattern sent to settings.js means the same in both languages."""
        self.assertNotIn("\\d", NUMBER_PATTERN)
        self.assertNotIn("\\s", NUMBER_PATTERN)

    def test_values_are_stripped_as_javascript_trims_them(self):
        """Test the whitespace set: JavaScript's trim(), not Python's strip()."""
        field = BY_KEY["top_tier_count"]
        for raw in ("﻿3", "　 3 ", "\t3\n"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_value(field, raw), (3, None))
        # Python strips these and JavaScript does not.
        for raw in ("\x1c3", "3\x85"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_value(field, raw), (None, ERROR_NUMBER))

    def test_switches_read_on_from_a_form_or_an_address(self):
        """Test the values a switch takes as on."""
        field = BY_KEY["top_tier_mode"]
        for raw, expected in (("on", True), ("1", True), ("true", True), ("", False), ("0", False)):
            with self.subTest(raw=raw):
                self.assertEqual(parse_value(field, raw), (expected, None))


class TestProjectsThatCannotBeDrawn(SettingsTestCase):
    """Test cases for an address naming no drawable project."""

    def test_a_project_that_is_not_there_is_not_found(self):
        """Test the 404 on the sheet and on a save."""
        self.assertEqual(self.client.get("/projects/Nope.pairrank/settings").status_code, 404)
        response = self.client.post(
            "/projects/Nope.pairrank/settings", data=valid_form(), follow_redirects=False
        )
        self.assertEqual(response.status_code, 404)

    def test_a_newer_file_gets_the_newer_version_page(self):
        """Test that a file from a newer application is not called damaged."""
        self.write("Future.pairrank", settings_data(format_version=CURRENT_FORMAT_VERSION + 1))
        response = self.client.get("/projects/Future.pairrank/settings")
        self.assertEqual(response.status_code, NEWER_FORMAT_STATUS)

    def test_a_damaged_file_gets_the_damaged_page(self):
        """Test that a file that will not read lands on the damaged page."""
        self.write("Broken.pairrank", "{ not json")
        response = self.client.get("/projects/Broken.pairrank/settings")
        self.assertEqual(response.status_code, DAMAGED_STATUS)

    def test_a_file_holding_an_out_of_range_value_opens_clamped(self):
        """Test the load decision: brought into range, not refused."""
        self.write(PROJECT, settings_data({"cross_category_rate": 1.5, "top_tier_count": 0}))
        with self.assertLogs("src.models.settings", level="WARNING"):
            body = self.sheet()
        self.assertEqual(value_of(body, "cross_category_rate"), "1.00")
        self.assertEqual(value_of(body, "top_tier_count"), "1")
        self.assertNotIn("is-error", body)


class TestEverySettingsPageReadsTheFile(SettingsTestCase):
    """Test cases for the sheet after another program saved the file."""

    def test_the_sheet_draws_what_the_file_now_says(self):
        """Test open_fresh: a GET after an outside save draws the new values."""
        self.sheet()
        self.write(PROJECT, settings_data({"weight_freshness": 4.0}))
        body = self.sheet()
        self.assertEqual(value_of(body, "weight_freshness"), "4.0")


class TestSettingsUnderARootPath(SettingsTestCase):
    """Test cases for the sheet behind a reverse proxy on a subpath."""

    root_path = "/rank"

    def test_every_address_the_sheet_builds_carries_the_prefix(self):
        """Test the form, Reset, the tabs and the save's redirect under /rank."""
        body = self.sheet()
        prefixed = f"/rank{SETTINGS_URL}"
        self.assertIn(f'action="{prefixed}"', body)
        self.assertIn(f'formaction="{prefixed}"', body)
        self.assertIn(f'<a href="{prefixed}" aria-current="page">', body)
        self.assertNotIn(f'"{SETTINGS_URL}', body)

        response = self.save(valid_form(weight_freshness="0.75"))
        self.assertTrue(response.headers["location"].startswith(f"{prefixed}?"))


if __name__ == "__main__":
    unittest.main()
