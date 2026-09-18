"""Tests for the sheet shell, its macros and the static assets behind them.

These are about the drawing rather than about the data: that a sheet comes back
with its frame, its zones and the standard title block on it, that the
stylesheets and fonts the page asks for are actually served, and that the three
accessibility decisions baked into the macros stay baked in. Five screens will
inherit them, so they are worth a test each here rather than five tests each
later.
"""

import re
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from src.web.app import STATIC_DIR, STATIC_MOUNT, create_app
from src.web.config import WebConfig


# Tags that never close, so they must not be pushed onto the tag stack when
# walking a page. The sheet uses link, meta and the SVG sprite's paths.
VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr", "path", "circle", "use",
    }
)

# Every static file base.html and placeholder.html ask for by name. Listed
# rather than globbed: the point is that the page's references resolve, and a
# glob would pass just as happily over a directory that had lost the file.
REFERENCED_ASSETS = (
    "css/sheet.css",
    "css/bom.css",
    "js/htmx.min.js",
    "fonts/barlow-400-latin.woff2",
    "fonts/jetbrains-mono-latin.woff2",
)


def ancestors_of(markup: str, element_id: str) -> list:
    """
    List the tags an element sits inside, outermost first.

    Args:
        markup: The rendered page.
        element_id: The id of the element to find.

    Returns:
        list: The ancestor tag names, or an empty list if the id is not there.
    """

    class Walker(HTMLParser):
        """Track the open tags and remember the stack at one element."""

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.found = None

        def handle_starttag(self, tag, attrs):
            """Record the stack when the wanted id opens, then push the tag."""
            if dict(attrs).get("id") == element_id and self.found is None:
                self.found = list(self.stack)
            if tag not in VOID_ELEMENTS:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            """Pop back to the matching open tag, if there is one."""
            if tag in self.stack:
                del self.stack[self.stack.index(tag):]

    walker = Walker()
    walker.feed(markup)
    return walker.found or []


def config_for(data_dir: Path, root_path: str = "") -> WebConfig:
    """
    Build a configuration pointing at a temporary data directory.

    Args:
        data_dir: The directory the application serves projects from.
        root_path: The subpath a reverse proxy would serve it under.

    Returns:
        WebConfig: A configuration with a fixed key.
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


class TemplateTestCase(unittest.TestCase):
    """Base case giving each test an application over a temporary directory."""

    root_path = ""

    def setUp(self):
        """Build an application with nothing to serve but the shell."""
        self.temp_dir = tempfile.mkdtemp()
        self.app = create_app(config_for(Path(self.temp_dir), self.root_path))
        self.client = TestClient(self.app)

    def tearDown(self):
        """Remove the data directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def render(self, source: str, **context) -> str:
        """
        Render a fragment against the application's own template environment.

        Args:
            source: The template text, which may import the macros.
            **context: Values for the template.

        Returns:
            str: The rendered markup.
        """
        return self.app.state.templates.env.from_string(source).render(**context)


class TestPlaceholderSheet(TemplateTestCase):
    """Test cases for the empty sheet the shell is checked against."""

    def setUp(self):
        """Fetch the sheet once; every test here reads the same page."""
        super().setUp()
        self.response = self.client.get("/_sheet")
        self.body = self.response.text

    def test_the_sheet_renders(self):
        """Test that the shell answers as a page."""
        self.assertEqual(self.response.status_code, 200)
        self.assertIn("text/html", self.response.headers["content-type"])

    def test_the_sheet_is_drawn_in_a_zoned_frame(self):
        """Test that the frame and its four zone rulers are on the sheet."""
        self.assertIn('<main class="frame"', self.body)
        self.assertIn('class="frame-inner', self.body)
        for side in ("top", "bottom", "left", "right"):
            with self.subTest(side=side):
                self.assertIn(f'class="zones zones-{side}"', self.body)

    def test_zone_numbers_run_high_to_low(self):
        """
        Test that the numbered rulers are listed 8 to 1.

        The stylesheet narrows a sheet to 6 or 4 zones by hiding list items
        from the left, so the order is what makes zone 1 stay in the
        lower-right corner at every width.
        """
        numbers = re.search(
            r'class="zones zones-top"[^>]*>(.*?)</ol>', self.body, re.S
        )
        self.assertIsNotNone(numbers)
        self.assertEqual(
            re.findall(r"<li>(\d)</li>", numbers.group(1)),
            ["8", "7", "6", "5", "4", "3", "2", "1"],
        )

    def test_the_sheet_closes_with_the_standard_title_block(self):
        """Test that the title block, its keys block and SHEET n OF N are drawn."""
        self.assertIn('class="titleblock tb-with-keys"', self.body)
        self.assertIn('class="tb-cell tb-keyblock"', self.body)
        self.assertIn('class="tb-cell tb-title span-3"', self.body)
        self.assertIn('class="tb-cell tb-file span-3"', self.body)
        self.assertIn('class="tb-cell tb-sheet span-2"', self.body)
        self.assertIn("1 of 1", self.body)

    def test_the_keys_block_lists_its_keys_as_ruled_legends(self):
        """Test that the keys block draws a legend per key, not bare text."""
        keys = re.search(r'class="tb-keylist">(.*?)</ul>', self.body, re.S)
        self.assertIsNotNone(keys)
        self.assertGreaterEqual(keys.group(1).count('class="key"'), 4)

    def test_the_sheet_has_no_rows(self):
        """Test that the empty sheet is empty, and says so."""
        self.assertNotIn('class="bom-row', self.body)
        self.assertIn('class="bom-empty"', self.body)

    def test_the_popover_host_is_outside_the_sheet(self):
        """
        Test that the callout host is not inside the region rows are swapped in.

        Phase 5a positions a callout in this element and a form may be open in
        it while the rows beneath are replaced, so it has to outlive them.
        Checked by walking the tree rather than by looking at offsets, because
        "after the sheet in the source" and "not inside the sheet" are not the
        same statement and only the second one is the invariant.
        """
        self.assertEqual(ancestors_of(self.body, "row-callout"), ["html", "body"])

    def test_the_page_pulls_its_script_and_styles_from_the_static_mount(self):
        """Test that nothing on the sheet is fetched from the internet."""
        for asset in REFERENCED_ASSETS:
            with self.subTest(asset=asset):
                self.assertIn(f'"{STATIC_MOUNT}/{asset}"', self.body)
        self.assertNotIn("fonts.googleapis.com", self.body)
        self.assertNotIn("fonts.gstatic.com", self.body)
        self.assertNotIn("//unpkg.com", self.body)

    def test_the_theme_follows_the_system_until_it_is_told_otherwise(self):
        """Test that no theme is forced onto the document by the server."""
        self.assertNotIn('data-theme="', self.body)
        self.assertIn("pairrank-theme", self.body)


class TestPlaceholderSheetUnderARootPath(TemplateTestCase):
    """Test cases for the shell behind a reverse proxy on a subpath."""

    root_path = "/rank"

    def test_static_urls_carry_the_proxy_prefix(self):
        """Test that the stylesheets are still reachable under the subpath."""
        client = TestClient(self.app, root_path=self.root_path)

        body = client.get("/rank/_sheet").text

        self.assertIn(f'"/rank{STATIC_MOUNT}/css/sheet.css"', body)

    def test_static_urls_are_paths_rather_than_absolute(self):
        """
        Test that an asset URL cannot carry the wrong scheme or host.

        url_for builds an absolute URL from the request, which a proxy running
        without --proxy-headers gets wrong; a page whose stylesheet 404s that
        way is not obviously broken, it is just unstyled.
        """
        client = TestClient(self.app, root_path=self.root_path)

        body = client.get("/rank/_sheet").text

        self.assertNotIn("http://testserver", body)


class TestStaticAssets(TemplateTestCase):
    """Test cases for the files the sheet asks the static mount for."""

    def test_every_referenced_asset_is_served(self):
        """Test that each file the page names comes back over the mount."""
        for asset in REFERENCED_ASSETS:
            with self.subTest(asset=asset):
                response = self.client.get(f"{STATIC_MOUNT}/{asset}")

                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.content), 0)

    def test_the_fonts_are_real_woff2(self):
        """
        Test that the font files are fonts.

        A failed download saved under a .woff2 name is served with a perfectly
        good 200 and renders nothing, so the signature is worth checking.
        """
        for path in sorted((STATIC_DIR / "fonts").glob("*.woff2")):
            with self.subTest(font=path.name):
                self.assertEqual(path.read_bytes()[:4], b"wOF2")

    def test_every_font_face_points_at_a_file_that_is_there(self):
        """Test that no @font-face rule outlives the file it names."""
        css = (STATIC_DIR / "css" / "sheet.css").read_text(encoding="utf-8")
        references = re.findall(r'url\("\.\./fonts/([^"]+)"\)', css)

        self.assertGreater(len(references), 0)
        for name in references:
            with self.subTest(font=name):
                self.assertTrue((STATIC_DIR / "fonts" / name).is_file())

    def test_the_fonts_ship_with_their_licences(self):
        """Test that the OFL text travels with the fonts, as the licence asks."""
        for name in ("OFL-Barlow.txt", "OFL-BarlowCondensed.txt", "OFL-JetBrainsMono.txt"):
            with self.subTest(licence=name):
                text = (STATIC_DIR / "fonts" / name).read_text(encoding="utf-8")

                self.assertIn("SIL OPEN FONT LICENSE", text.upper())

    def test_the_stylesheets_keep_no_mockup_only_rules(self):
        """Test that the state switcher's styles left with the state switcher."""
        for name in ("sheet.css", "bom.css", "compare.css", "settings.css"):
            with self.subTest(stylesheet=name):
                css = (STATIC_DIR / "css" / name).read_text(encoding="utf-8")

                self.assertNotIn(".mockup-controls", css)


class TestSheetMacros(TemplateTestCase):
    """Test cases for the accessibility decisions the macros carry."""

    def test_a_balloon_states_its_slot_in_text_a_screen_reader_reads(self):
        """
        Test that the full slot name is real text, not an aria-label.

        DESIGN.md's open issues name this one: a span with no role and an
        aria-label is ignored by several screen readers, so the short label
        would be all that was announced.
        """
        markup = self.render(
            '{% from "macros/sheet.html" import balloon %}'
            '{{ balloon("Ap", full="Apostrophe") }}'
        )

        self.assertIn('<span class="visually-hidden">Slot Apostrophe</span>', markup)
        self.assertIn('title="Slot Apostrophe"', markup)
        self.assertIn('<span aria-hidden="true">Ap</span>', markup)
        self.assertNotIn("aria-label", markup)

    def test_an_item_with_no_slot_gets_a_dashed_balloon_and_no_announcement(self):
        """Test that the empty ring is silent, because a NO SLOT tag says it."""
        markup = self.render(
            '{% from "macros/sheet.html" import balloon %}{{ balloon(none) }}'
        )

        self.assertIn("balloon is-empty", markup)
        self.assertIn('aria-hidden="true"', markup)

    def test_a_row_tag_sits_outside_the_name_that_truncates(self):
        """
        Test that a RETIRED tag cannot be eaten by the name's ellipsis.

        The tag is the non-colour half of the retired signal, and the primary
        user has deuteranopia, so ink 3 on its own is not a signal at all.
        """
        markup = self.render(
            '{% from "macros/parts_list.html" import name_cell %}'
            '{{ name_cell("A name long enough to truncate", tags=["Retired"]) }}'
        )

        name = re.search(r'<span class="bom-name">(.*?)</span>', markup, re.S)
        self.assertIsNotNone(name)
        self.assertNotIn("tag", name.group(1))
        self.assertIn('class="bom-nameline"', markup)
        self.assertIn('<span class="tag">Retired</span>', markup)

    def test_a_row_carries_its_state_in_classes_the_engine_reads(self):
        """Test that selection and retirement are on the row, not its cells."""
        markup = self.render(
            '{% from "macros/parts_list.html" import parts_row %}'
            '{% call parts_row("x1", selected=true, retired=true) %}<td></td>{% endcall %}'
        )

        self.assertIn("bom-row", markup)
        self.assertIn("is-selected", markup)
        self.assertIn("is-retired", markup)
        self.assertIn('data-id="x1"', markup)
        self.assertIn('aria-selected="true"', markup)
        self.assertIn('tabindex="-1"', markup)

    def test_a_parts_list_repeats_its_columns_as_drafting_headers(self):
        """Test that the header row is built from the column definitions."""
        markup = self.render(
            '{% from "macros/parts_list.html" import parts_list %}'
            '{% call parts_list(columns, "Items") %}{% endcall %}',
            columns=[
                {"label": "Slot", "class": "c-find", "width": "3.5rem"},
                {"label": "Name"},
            ],
        )

        self.assertIn('<th class="c-find" style="width:3.5rem">Slot</th>', markup)
        self.assertIn("<th>Name</th>", markup)
        self.assertIn('aria-label="Items"', markup)

    def test_the_callout_is_a_group_rather_than_a_dialog(self):
        """
        Test that the popover does not claim modality it does not have.

        The sheet behind the callout stays live and focus is not trapped, so
        role="dialog" would promise something the design deliberately refuses.
        """
        markup = self.render(
            '{% from "macros/popover.html" import popover %}'
            '{% call popover("Gateron Oil King") %}<p>x</p>{% endcall %}'
        )

        self.assertIn('role="group"', markup)
        self.assertIn('aria-label="Gateron Oil King"', markup)
        self.assertIn("bom-callout", markup)


class TestErrorPagesOnTheShell(TemplateTestCase):
    """Test cases for the error pages now that they are drawn as sheets."""

    def test_a_missing_page_is_drawn_in_the_frame(self):
        """Test that an error page is a sheet of the same set."""
        response = self.client.get("/no-such-sheet")

        self.assertEqual(response.status_code, 404)
        self.assertIn('<main class="frame"', response.text)
        self.assertIn('class="zones zones-top"', response.text)
        self.assertIn('class="error-sheet"', response.text)
        self.assertIn('class="error-page"', response.text)

    def test_an_error_page_is_styled(self):
        """Test that the page reparented onto the shell picked up sheet.css."""
        response = self.client.get("/no-such-sheet")

        self.assertIn(f'"{STATIC_MOUNT}/css/sheet.css"', response.text)

    def test_an_error_page_still_offers_the_way_back(self):
        """Test that reparenting did not lose the link home."""
        response = self.client.get("/no-such-sheet")

        self.assertIn('class="error-actions"', response.text)
        self.assertIn('href="/"', response.text)

    def test_a_refused_method_is_drawn_as_a_sheet_too(self):
        """
        Test that the generic page renders, and says which status it is.

        It is the one error page nothing reached before: the handler passed the
        status both positionally and by keyword, so every non-404 HTTPException
        raised a TypeError from inside the handler meant to answer it.
        """
        response = self.client.post("/_sheet")

        self.assertEqual(response.status_code, 405)
        self.assertIn('class="error-sheet"', response.text)
        self.assertIn("405", response.text)

    def test_an_error_page_names_itself_in_the_title_and_the_heading(self):
        """Test that the heading still falls back to the page's own title."""
        response = self.client.get("/no-such-sheet")

        self.assertIn("<title>Not found &middot; Pairwise Ranking</title>", response.text)
        self.assertIn("<h1>Not found</h1>", response.text)


if __name__ == "__main__":
    unittest.main()
