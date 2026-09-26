"""Route tests for the Items sheet's callouts, forms and mutations.

Chunk 6b's half of the screen. Three kinds of test, one per shape of route:

- **A callout** is asked for at its fragment address and taken apart: which
  actions, which keys they are declared under, where they point.
- **A page state** is asked for at its address - ``form``, ``item`` and a
  refused draft - and the row it opens the form on is cut out of the page.
- **A mutation** is posted without following its 303, and judged by the file
  it left in the data directory and the address it answered with. A refused
  one must leave the directory byte for byte as it found it.

As in ``tests/test_web_items.py``, words on the page are the capture pass's
business; the few asserted here are the Last change sentences, because which
item they name is the point of them.
"""

import html
import json
import re
import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from src.web.routes.items import RELOADED_NOTE
from tests.test_web_items import (
    ITEMS,
    ITEMS_URL,
    PROJECT,
    ItemsTestCase,
    cell_text,
    element,
    item,
    project_data,
    row_ids,
)
from tests.test_web_projects import row_of


def vote(winner: str, loser: str, vote_id: str) -> dict:
    """
    Build one vote entry.

    Args:
        winner: The winning item's id.
        loser: The losing item's id.
        vote_id: The vote's id.

    Returns:
        dict: The entry.
    """
    return {
        "id": vote_id,
        "winner_id": winner,
        "loser_id": loser,
        "weight": 1.0,
        "timestamp": "2026-09-16T21:00:00",
    }


# Oil King took part in two votes and Cream in one of them; deleting Oil King
# takes both, and must leave Cream's other vote alone.
VOTES = [
    vote("oil", "cream", "v1"),
    vote("jade", "oil", "v2"),
    vote("cream", "jade", "v3"),
]


def opening_of(body: str) -> str:
    """
    Find the form a sheet's address opens: the callout its boot script asks for.

    Args:
        body: The sheet.

    Returns:
        str: The address fetched once for the arriving selection, or empty when
        the page opens no form on a row.
    """
    found = re.search(r"sheet\.select\((\"[^\"]*\"), \{ callout: (\"[^\"]*\") \}\)", body)
    return json.loads(found.group(2)) if found else ""


class ActionsTestCase(ItemsTestCase):
    """Base case with votes in the project and the register's post helpers."""

    def seed(self):
        """Write the project, with votes this time."""
        self.write(PROJECT, project_data(votes=VOTES))

    def stored(self) -> dict:
        """
        Read the project file back.

        Returns:
            dict: The project as saved.
        """
        return json.loads((self.data_dir / PROJECT).read_text(encoding="utf-8"))

    def stored_item(self, item_id: str) -> dict:
        """
        Read one item back from the file.

        Args:
            item_id: The item.

        Returns:
            dict: Its entry, or None when the file does not hold it.
        """
        return next((i for i in self.stored()["items"] if i["id"] == item_id), None)

    def snapshot(self) -> dict:
        """
        Read every file in the data directory.

        Returns:
            dict: File name to bytes.
        """
        return {p.name: p.read_bytes() for p in self.data_dir.iterdir() if p.is_file()}

    def post(self, path: str, data: dict = None):
        """
        Post a form without following the redirect that comes back.

        Args:
            path: The path under the sheet, e.g. "oil/retire".
            data: The form fields.

        Returns:
            The response.
        """
        return self.client.post(
            f"{ITEMS_URL}/{path}", data=data or {}, follow_redirects=False
        )

    def redirect_of(self, response) -> tuple:
        """
        Take apart the 303 a mutation answered with.

        Args:
            response: The response.

        Returns:
            tuple: Its path, and its query as a mapping of single values.
        """
        self.assertEqual(response.status_code, 303)
        parsed = urlparse(response.headers["location"])
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        return parsed.path, query

    def fragment(self, path: str) -> str:
        """
        Ask for one callout fragment.

        Args:
            path: The path under the sheet, with its query.

        Returns:
            str: The fragment, after asserting it was drawn.
        """
        response = self.client.get(f"{ITEMS_URL}/{path}")
        self.assertEqual(response.status_code, 200)
        return response.text

    def landed(self, response) -> str:
        """
        Follow a mutation's 303 and draw the sheet it lands on.

        Args:
            response: The 303.

        Returns:
            str: The page.
        """
        self.assertEqual(response.status_code, 303)
        page = self.client.get(response.headers["location"])
        self.assertEqual(page.status_code, 200)
        return page.text


def actions_of(body: str) -> dict:
    """
    List a callout's action cells.

    Args:
        body: The fragment.

    Returns:
        dict: Each cell's data-action to its opening tag.
    """
    return {
        match.group(1): match.group(0)
        for match in re.finditer(
            r'<button class="strip-action" data-action="([^"]+)"[^>]*>', body
        )
    }


def field_tag(body: str, field_id: str) -> str:
    """
    Cut one form field's opening tag out of a fragment.

    Args:
        body: The fragment.
        field_id: The field's id.

    Returns:
        str: The tag, or an empty string.
    """
    return element(body, rf'<(?:input|textarea)[^>]*id="{field_id}"')


class TestRowCallout(ActionsTestCase):
    """Test cases for the actions a row's callout offers."""

    def test_every_row_asks_for_its_own_callout(self):
        """Test that each row's hookup names its own item and carries the view."""
        body = self.sheet("q=cherry&retired=1")
        row = row_of(body, "blue")

        self.assertIn(
            f'hx-get="{ITEMS_URL}/blue/callout?q=cherry&amp;retired=1"', row
        )

    def test_an_active_item_offers_edit_retire_replace_and_delete(self):
        """Test the four actions, the keys they answer to, and where they point."""
        body = self.fragment("oil/callout")
        actions = actions_of(body)

        self.assertEqual(list(actions), ["edit", "retire", "replace", "delete"])
        for action, key in (
            ("edit", "Enter"), ("retire", "R"), ("replace", "P"), ("delete", "Delete"),
        ):
            with self.subTest(action=action):
                self.assertIn(f'data-sheet-key="{key}"', actions[action])
                self.assertIn(f'aria-keyshortcuts="{key}"', actions[action])
        self.assertIn(f'hx-get="{ITEMS_URL}/oil/edit"', actions["edit"])
        self.assertIn(f'hx-get="{ITEMS_URL}/oil/replace"', actions["replace"])
        self.assertIn(f'hx-get="{ITEMS_URL}/oil/delete"', actions["delete"])
        self.assertIn('aria-label="(10) Gateron Oil King"', body)

    def test_retire_posts_its_own_form_outside_the_strip(self):
        """
        Test that Retire submits a POST form that is not a child of the strip.

        The phone rule that widens an odd last cell counts the strip's
        children, so the form lives beside it.
        """
        body = self.fragment("oil/callout?q=oil")

        self.assertIn('type="submit" form="retire-form"', actions_of(body)["retire"])
        self.assertRegex(
            body,
            rf'<form id="retire-form" method="post" action="{ITEMS_URL}/oil/retire" hidden>'
            r'<input type="hidden" name="q" value="oil"></form>\s*<div class="strip-actions">',
        )

    def test_a_retired_item_offers_reactivate_and_delete(self):
        """Test the retired row's two actions, and no Retire form."""
        body = self.fragment("blue/callout")
        actions = actions_of(body)

        self.assertEqual(list(actions), ["reactivate", "delete"])
        self.assertIn('data-sheet-key="A"', actions["reactivate"])
        self.assertNotIn("retire-form", body)

    def test_an_item_the_project_does_not_hold_is_not_found(self):
        """Test the 404 for an id that is not there."""
        self.assertEqual(self.client.get(f"{ITEMS_URL}/nope/callout").status_code, 404)


class TestItemForms(ActionsTestCase):
    """Test cases for the four forms, fresh."""

    def test_edit_is_prefilled_and_focuses_the_name(self):
        """Test the edit form: the item's values, the name focused, Save and Cancel wired."""
        body = self.fragment("oil/edit?category=Linear")

        self.assertIn('value="Gateron Oil King"', field_tag(body, "f-name"))
        self.assertIn("autofocus", field_tag(body, "f-name"))
        self.assertNotIn("aria-invalid", body)
        self.assertIn('value="10"', field_tag(body, "f-slot"))
        self.assertIn("Deep, muted.</textarea>", body)
        self.assertIn(f'action="{ITEMS_URL}/oil/edit"', body)
        self.assertIn('<input type="hidden" name="category" value="Linear">', body)
        self.assertIn('data-sheet-key="Enter" aria-keyshortcuts="Enter">Save', body)
        cancel = element(body, r'<a class="cell-button" href=')
        self.assertIn(f'href="{ITEMS_URL}?selected=oil&amp;category=Linear"', cancel)
        self.assertIn('data-sheet-key="Escape"', cancel)

    def test_edit_counts_the_item_s_own_slot_as_free(self):
        """Test that the free list offers the slot the item is sitting in."""
        body = self.fragment("oil/edit")

        self.assertIn('<option value="10">', body)
        self.assertNotIn('<option value="1">', body)

    def test_new_offers_the_first_free_slot(self):
        """Test the Add form: empty, in the first free slot, the name focused."""
        body = self.fragment("new")

        self.assertIn('value=""', field_tag(body, "f-name"))
        self.assertIn("autofocus", field_tag(body, "f-name"))
        self.assertIn('value="2"', field_tag(body, "f-slot"))
        self.assertIn(f'action="{ITEMS_URL}/new"', body)
        self.assertIn(f'href="{ITEMS_URL}"', element(body, r'<a class="cell-button"'))

    def test_replace_inherits_the_slot_and_category(self):
        """Test that Replace prefills what the successor takes over, and says so."""
        body = self.fragment("oil/replace")

        self.assertIn('value=""', field_tag(body, "f-name"))
        self.assertIn('value="Linear"', field_tag(body, "f-cat"))
        self.assertIn('value="10"', field_tag(body, "f-slot"))
        self.assertIn("Saving retires Gateron Oil King", body)

    def test_reactivate_asks_only_for_a_slot(self):
        """Test that Reactivate draws the slot field alone, focused, in a free slot."""
        body = self.fragment("blue/reactivate")

        self.assertEqual(field_tag(body, "f-name"), "")
        self.assertIn("autofocus", field_tag(body, "f-slot"))
        self.assertIn('value="2"', field_tag(body, "f-slot"))
        self.assertIn('data-sheet-key="Enter" aria-keyshortcuts="Enter">Reactivate', body)

    def test_a_board_with_no_free_slot_says_how_to_free_one(self):
        """Test the slot hint on a full board."""
        self.write(PROJECT, project_data(slots=["1", "10", "Apostrophe"]))

        body = self.fragment("new")

        self.assertIn('value=""', field_tag(body, "f-slot"))
        self.assertIn("No free slots.", body)

    def test_the_form_offers_the_project_s_categories_and_free_slots(self):
        """Test the two datalists the category and slot fields suggest from."""
        body = self.fragment("new")

        categories = re.search(r'<datalist id="dl-categories">(.*?)</datalist>', body).group(1)
        slots = re.search(r'<datalist id="dl-slots">(.*?)</datalist>', body).group(1)
        self.assertEqual(re.findall(r'value="([^"]+)"', categories), ["Clicky", "Linear", "Tactile"])
        self.assertEqual(re.findall(r'value="([^"]+)"', slots), ["2", "Enter"])
        self.assertIn('list="dl-categories"', field_tag(body, "f-cat"))
        self.assertIn('list="dl-slots"', field_tag(body, "f-slot"))

    def test_forms_a_row_does_not_offer_are_not_found(self):
        """Test the 404s: a retired item has no edit or replace, an active one no reactivate."""
        for path in ("blue/edit", "blue/replace", "oil/reactivate", "oil/nonsense"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(f"{ITEMS_URL}/{path}").status_code, 404)


class TestDeleteConfirmation(ActionsTestCase):
    """Test cases for the delete confirmation."""

    def test_the_question_counts_the_votes_that_go_with_it(self):
        """Test the question, the focused Delete and its keys, and the posted form."""
        body = self.fragment("oil/delete?retired=1")

        self.assertIn("Delete (10) Gateron Oil King and its 2 votes?", html.unescape(body))
        self.assertIn('role="alertdialog"', body)
        button = element(body, r'<button class="cell-button is-danger"')
        self.assertIn('form="delete-form"', button)
        self.assertIn("autofocus", button)
        self.assertIn('data-sheet-key="Delete Backspace"', button)
        self.assertRegex(
            body,
            rf'<form id="delete-form" method="post" action="{ITEMS_URL}/oil/delete" hidden>'
            r'<input type="hidden" name="retired" value="1"></form>',
        )

    def test_a_retired_item_is_not_offered_retirement_instead(self):
        """Test that the gentler way is only offered to an item that can take it."""
        body = html.unescape(self.fragment("blue/delete"))

        self.assertIn("Delete Cherry MX Blue?", body)
        self.assertNotIn("Retire keeps the votes", body)


class TestFormAddresses(ActionsTestCase):
    """Test cases for the page addresses that open a form on the sheet."""

    def test_form_new_draws_and_selects_a_ghost_row(self):
        """Test the ghost row: first, new, tagged, selected, and asking for Add."""
        body = self.sheet("form=new&q=e")

        self.assertEqual(row_ids(body)[0], "__new")
        ghost = row_of(body, "__new")
        self.assertIn("is-new", ghost)
        self.assertIn(f'hx-get="{ITEMS_URL}/new?q=e"', ghost)
        self.assertIn('sheet.select("__new")', body)

    def test_form_new_on_an_empty_project_still_draws_a_table(self):
        """Test that the ghost row needs no other row to hang on."""
        self.write(PROJECT, project_data(items=[]))

        body = self.sheet("form=new")

        self.assertEqual(row_ids(body), ["__new"])

    def test_form_edit_opens_on_the_item_s_row(self):
        """Test that the arriving selection asks for the form, once."""
        body = self.sheet("form=edit&item=oil")

        self.assertIn('sheet.select("oil", { callout: ', body)
        self.assertEqual(opening_of(body), f"{ITEMS_URL}/oil/edit")

    def test_the_row_itself_still_asks_for_its_actions(self):
        """Test that selecting the row again shows its actions, not the form."""
        for query in ("form=edit&item=oil", "form=delete&item=oil",
                      "form=edit&item=oil&submitted=1&name=&slot=1"):
            with self.subTest(query=query):
                body = self.sheet(query)
                self.assertIn(f'hx-get="{ITEMS_URL}/oil/callout"', row_of(body, "oil"))
                self.assertIn(f'hx-get="{ITEMS_URL}/jade/callout"', row_of(body, "jade"))

    def test_a_plain_selection_opens_no_form(self):
        """Test that `selected` alone selects the row with its own callout."""
        body = self.sheet("selected=oil")

        self.assertIn('sheet.select("oil");', body)
        self.assertEqual(opening_of(body), "")

    def test_a_refused_draft_is_carried_to_the_fragment(self):
        """Test that the page hands the draft on to the form it opens."""
        body = self.sheet("form=replace&item=oil&submitted=1&name=&cat=Linear&slot=1")
        hookup = opening_of(body)
        query = parse_qs(urlparse(hookup).query)

        self.assertEqual(query["submitted"], ["1"])
        self.assertEqual(query["slot"], ["1"])
        self.assertEqual(query["cat"], ["Linear"])

    def test_a_mistyped_submitted_opens_a_fresh_form(self):
        """
        Test that `submitted` other than 1 is no draft, not FastAPI's 422.

        On the page, which hands no draft on to the form, and on the fragment,
        which draws the item's own fields with no error.
        """
        for value in ("yes", "on", "2", "1.0"):
            with self.subTest(value=value):
                page = self.client.get(
                    f"{ITEMS_URL}?form=edit&item=oil&submitted={value}&name="
                )
                self.assertEqual(page.status_code, 200)
                self.assertIn("text/html", page.headers["content-type"])
                self.assertEqual(opening_of(page.text), f"{ITEMS_URL}/oil/edit")

                form = self.client.get(f"{ITEMS_URL}/oil/edit?submitted={value}&name=")
                self.assertEqual(form.status_code, 200)
                self.assertIn("text/html", form.headers["content-type"])
                self.assertNotIn('aria-invalid="true"', form.text)
                self.assertIn('value="Gateron Oil King"', field_tag(form.text, "f-name"))

    def test_a_form_the_row_cannot_have_is_no_form(self):
        """Test that a row not drawn, or not offering the form, opens none."""
        for query in ("form=edit&item=blue&retired=1", "form=reactivate&item=blue",
                      "form=edit&item=nope", "form=sideways&item=oil"):
            with self.subTest(query=query):
                body = self.sheet(query)
                self.assertNotRegex(body, r'/items/\w+/(edit|reactivate)')
                self.assertNotIn("__new", body)


class TestAddItem(ActionsTestCase):
    """Test cases for posting the Add form."""

    def test_an_item_is_added_and_selected(self):
        """Test the new item in the file, the 303 onto it, and the view kept."""
        response = self.post(
            "new",
            {"name": " Holy Panda ", "cat": "Tactile", "slot": "2", "desc": "", "q": "a"},
        )

        path, query = self.redirect_of(response)
        added = next(i for i in self.stored()["items"] if i["name"] == "Holy Panda")
        self.assertEqual((added["identifier"], added["category"]), ("2", "Tactile"))
        self.assertEqual(path, ITEMS_URL)
        self.assertEqual(
            query,
            {"selected": added["id"], "done": "added", "item": added["id"], "q": "a"},
        )
        self.assertEqual(
            cell_text(self.landed(response), "tb-last").rsplit(" · ", 1)[0],
            "Added (2) Holy Panda",
        )

    def test_an_empty_category_becomes_the_default(self):
        """Test the validator's rule, which is the desktop's."""
        self.post("new", {"name": "Plain"})

        added = next(i for i in self.stored()["items"] if i["name"] == "Plain")
        self.assertEqual(added["category"], "Default")

    def test_a_missing_name_is_refused_with_the_draft(self):
        """Test the refusal: nothing written, and back to the form with the draft."""
        before = self.snapshot()

        response = self.post("new", {"name": "  ", "cat": "Linear", "slot": "Enter"})

        self.assertEqual(self.snapshot(), before)
        path, query = self.redirect_of(response)
        self.assertEqual(path, ITEMS_URL)
        self.assertEqual(
            query, {"form": "new", "submitted": "1", "cat": "Linear", "slot": "Enter"}
        )

    def test_the_refused_form_draws_its_error_on_the_name(self):
        """Test the inline error, aria-invalid, and the focus on the refused field."""
        body = self.fragment("new?submitted=1&cat=Linear&slot=Enter")

        name = field_tag(body, "f-name")
        self.assertIn('aria-invalid="true"', name)
        self.assertIn('aria-describedby="err-name"', name)
        self.assertIn("autofocus", name)
        self.assertIn('<p class="field-error" id="err-name">', body)
        self.assertIn('value="Enter"', field_tag(body, "f-slot"))

    def test_a_taken_slot_is_refused(self):
        """Test that a slot another active item holds cannot be added into."""
        before = self.snapshot()

        response = self.post("new", {"name": "Holy Panda", "slot": "1"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response)[1]["slot"], "1")

    def test_the_refused_form_names_the_holder_and_the_free_slots(self):
        """Test the slot error: the field refused, the holder and the free list."""
        body = self.fragment("new?submitted=1&name=Holy+Panda&slot=1")

        slot = field_tag(body, "f-slot")
        self.assertIn('aria-invalid="true"', slot)
        self.assertIn("autofocus", slot)
        self.assertNotIn("autofocus", field_tag(body, "f-name"))
        error = re.search(r'<p class="field-error" id="err-slot">.*?</p>', body, re.S).group(0)
        self.assertIn("NovelKeys Cream", error)
        self.assertIn('<span class="num">2, Enter</span>', error)

    def test_a_retired_item_s_old_slot_is_not_taken(self):
        """Test that only active items hold slots."""
        self.write(PROJECT, project_data(items=ITEMS + [item("gone", "Gone", slot="2", retired=True)]))

        response = self.post("new", {"name": "Holy Panda", "slot": "2"})

        self.assertEqual(self.redirect_of(response)[1]["done"], "added")

    def test_free_text_is_accepted_beside_a_slot_list(self):
        """Test the desktop's rule: a slot list is a suggestion, not a closed set."""
        response = self.post("new", {"name": "Spare", "slot": "Shelf"})

        self.assertEqual(self.redirect_of(response)[1]["done"], "added")


class TestEditItem(ActionsTestCase):
    """Test cases for posting the edit form."""

    def test_an_edit_is_saved_and_the_item_stays_selected(self):
        """Test the edited item in the file and the 303 back onto it."""
        response = self.post(
            "oil/edit",
            {"name": "Oil King", "cat": "Linear", "slot": "Enter", "desc": "Thock.",
             "category": "Linear", "retired": "1"},
        )

        stored = self.stored_item("oil")
        self.assertEqual(
            (stored["name"], stored["identifier"], stored["description"]),
            ("Oil King", "Enter", "Thock."),
        )
        self.assertEqual(
            self.redirect_of(response)[1],
            {"selected": "oil", "done": "edited", "item": "oil",
             "category": "Linear", "retired": "1"},
        )

    def test_last_change_names_the_item_as_it_now_is(self):
        """Test the mockup's sentence, with the new name and slot."""
        page = self.landed(self.post("oil/edit", {"name": "Oil King", "slot": "Enter"}))

        self.assertEqual(cell_text(page, "tb-last").rsplit(" · ", 1)[0], "Edited (Enter) Oil King")

    def test_keeping_its_own_slot_is_not_a_conflict(self):
        """Test that the item's own slot is not counted as taken."""
        response = self.post("oil/edit", {"name": "Oil King", "slot": "10"})

        self.assertEqual(self.redirect_of(response)[1]["done"], "edited")
        self.assertEqual(self.stored_item("oil")["identifier"], "10")

    def test_a_missing_name_is_refused(self):
        """Test the refusal back to the edit form on the item's row."""
        before = self.snapshot()

        response = self.post("oil/edit", {"name": "", "slot": "10"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            self.redirect_of(response)[1],
            {"form": "edit", "item": "oil", "submitted": "1", "slot": "10"},
        )

    def test_a_slot_another_item_holds_is_refused(self):
        """Test the mockup's slot conflict."""
        before = self.snapshot()

        response = self.post("oil/edit", {"name": "Gateron Oil King", "slot": "Apostrophe"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response)[1]["form"], "edit")

    def test_the_refused_edit_draws_the_conflict_on_the_row(self):
        """Test the slot-conflict state end to end: page, then its row's fragment."""
        response = self.post("oil/edit", {"name": "Gateron Oil King", "slot": "Apostrophe"})
        page = self.landed(response)
        hookup = opening_of(page)

        body = self.client.get(hookup).text

        self.assertIn('aria-invalid="true"', field_tag(body, "f-slot"))
        self.assertIn("Kailh Box Jade", body)
        self.assertIn('value="Gateron Oil King"', field_tag(body, "f-name"))

    def test_a_retired_item_is_not_edited(self):
        """Test that a post the row does not offer changes nothing and lands on the row."""
        before = self.snapshot()

        response = self.post("blue/edit", {"name": "Blue", "retired": "1"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response)[1], {"selected": "blue", "retired": "1"})

    def test_an_item_that_has_gone_lands_on_the_sheet(self):
        """Test the second-tab case: nothing changed, nothing selected."""
        before = self.snapshot()

        response = self.post("nope/edit", {"name": "Anything"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response), (ITEMS_URL, {}))


class TestReplaceItem(ActionsTestCase):
    """Test cases for posting the replace form."""

    def test_the_successor_takes_the_slot_and_is_selected(self):
        """Test the old item retired and pointing at its successor, which holds the slot."""
        response = self.post("oil/replace", {"name": "Oil King V2", "cat": "Linear", "slot": "10"})

        old = self.stored_item("oil")
        new = next(i for i in self.stored()["items"] if i["name"] == "Oil King V2")
        self.assertEqual((old["status"], old["identifier"]), ("retired", ""))
        self.assertEqual(old["replaced_by"], new["id"])
        self.assertEqual((new["status"], new["identifier"]), ("active", "10"))
        self.assertEqual(
            self.redirect_of(response)[1],
            {"selected": new["id"], "done": "replaced", "item": new["id"]},
        )
        self.assertEqual(
            cell_text(self.landed(response), "tb-last").rsplit(" · ", 1)[0],
            "Replaced Gateron Oil King with (10) Oil King V2",
        )

    def test_a_missing_name_is_refused(self):
        """Test the refusal, with the draft."""
        before = self.snapshot()

        response = self.post("oil/replace", {"name": "", "cat": "Linear", "slot": "10"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response)[1]["form"], "replace")

    def test_a_slot_another_item_holds_is_refused(self):
        """Test that the successor may take its predecessor's slot and no other held one."""
        before = self.snapshot()

        response = self.post("oil/replace", {"name": "Oil King V2", "slot": "1"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response)[1]["item"], "oil")

    def test_the_refused_replace_is_drawn_on_the_old_item_s_row(self):
        """Test the refusal's address end to end: the row asks for its replace form, refused."""
        response = self.post("oil/replace", {"name": "", "cat": "Linear", "slot": "10"})
        page = self.landed(response)
        hookup = opening_of(page)

        self.assertEqual(urlparse(hookup).path, f"{ITEMS_URL}/oil/replace")
        body = self.client.get(hookup).text
        self.assertIn('aria-invalid="true"', field_tag(body, "f-name"))
        self.assertIn('value="10"', field_tag(body, "f-slot"))

    def test_an_empty_category_becomes_the_default(self):
        """Test the validator's rule, as Add has it, rather than the old item's category."""
        self.post("oil/replace", {"name": "Oil King V2", "cat": " ", "slot": "10"})

        new = next(i for i in self.stored()["items"] if i["name"] == "Oil King V2")
        self.assertEqual(new["category"], "Default")

    def test_a_retired_item_is_not_replaced(self):
        """Test that a post the row does not offer changes nothing and lands on the row."""
        before = self.snapshot()

        response = self.post("blue/replace", {"name": "Blue V2", "retired": "1"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response)[1], {"selected": "blue", "retired": "1"})

    def test_an_item_that_has_gone_lands_on_the_sheet(self):
        """Test the second-tab case: nothing changed, nothing selected."""
        before = self.snapshot()

        response = self.post("nope/replace", {"name": "Anything"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response), (ITEMS_URL, {}))


class TestReactivateItem(ActionsTestCase):
    """Test cases for posting the reactivate form."""

    def test_the_item_comes_back_in_the_slot_given(self):
        """Test the item active again, in its slot, still selected."""
        response = self.post("blue/reactivate", {"slot": "Enter", "retired": "1"})

        stored = self.stored_item("blue")
        self.assertEqual((stored["status"], stored["identifier"]), ("active", "Enter"))
        self.assertEqual(
            self.redirect_of(response)[1],
            {"selected": "blue", "done": "reactivated", "item": "blue", "retired": "1"},
        )

    def test_a_taken_slot_is_refused(self):
        """Test the one error Reactivate can have."""
        before = self.snapshot()

        response = self.post("blue/reactivate", {"slot": "10", "retired": "1"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            self.redirect_of(response)[1],
            {"form": "reactivate", "item": "blue", "submitted": "1", "slot": "10",
             "retired": "1"},
        )
        body = self.fragment("blue/reactivate?submitted=1&slot=10&retired=1")
        self.assertIn('aria-invalid="true"', field_tag(body, "f-slot"))

    def test_an_active_item_is_not_reactivated(self):
        """Test that the post changes nothing when the row does not offer it."""
        before = self.snapshot()

        self.post("oil/reactivate", {"slot": "2"})

        self.assertEqual(self.snapshot(), before)

    def test_an_item_that_has_gone_lands_on_the_sheet(self):
        """Test the second-tab case: nothing changed, nothing selected."""
        before = self.snapshot()

        response = self.post("nope/reactivate", {"slot": "2", "retired": "1"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response), (ITEMS_URL, {"retired": "1"}))

    def test_last_change_names_the_item_in_its_new_slot(self):
        """Test the mockup's sentence."""
        page = self.landed(self.post("blue/reactivate", {"slot": "Enter", "retired": "1"}))

        self.assertEqual(
            cell_text(page, "tb-last").rsplit(" · ", 1)[0], "Reactivated (Enter) Cherry MX Blue"
        )


class TestRetireItem(ActionsTestCase):
    """Test cases for Retire, which posts at once."""

    def test_retiring_frees_the_slot_and_keeps_the_votes(self):
        """Test the file: retired, no slot, every vote still there."""
        self.post("oil/retire")

        stored = self.stored_item("oil")
        self.assertEqual((stored["status"], stored["identifier"]), ("retired", ""))
        self.assertEqual(len(self.stored()["votes"]), 3)

    def test_the_selection_moves_to_the_next_row(self):
        """Test the mockup's focus rule, when retired items are hidden."""
        response = self.post("oil/retire", {"q": ""})

        self.assertEqual(
            self.redirect_of(response)[1],
            {"selected": "jade", "done": "retired", "item": "oil"},
        )

    def test_the_last_row_hands_the_selection_back(self):
        """Test that retiring the last row selects the one before it."""
        response = self.post("brown/retire")

        self.assertEqual(self.redirect_of(response)[1]["selected"], "alpaca")

    def test_the_selection_stays_when_retired_items_are_shown(self):
        """Test that the row does not leave a sheet that shows retired items."""
        response = self.post("oil/retire", {"retired": "1"})

        self.assertEqual(self.redirect_of(response)[1]["selected"], "oil")

    def test_the_next_row_is_the_next_one_in_the_view(self):
        """Test that the neighbour is chosen among the rows the filter draws."""
        response = self.post("cream/retire", {"q": "k"})

        # "k" draws Oil King and Box Jade and nothing else of the active items.
        self.assertEqual(self.redirect_of(response)[1]["selected"], "oil")

    def test_last_change_names_the_item_and_the_slot_freed(self):
        """Test the mockup's sentence."""
        page = self.landed(self.post("oil/retire"))

        self.assertEqual(
            cell_text(page, "tb-last").rsplit(" · ", 1)[0],
            "Retired Gateron Oil King · slot 10 freed",
        )

    def test_a_retired_item_is_not_retired_again(self):
        """Test that a post the row does not offer changes nothing."""
        before = self.snapshot()

        self.post("blue/retire")

        self.assertEqual(self.snapshot(), before)

    def test_an_item_that_has_gone_changes_nothing(self):
        """Test the double submit from a second tab."""
        before = self.snapshot()

        response = self.post("nope/retire", {"q": "cherry"})

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response), (ITEMS_URL, {"q": "cherry"}))


class TestDeleteItem(ActionsTestCase):
    """Test cases for Delete, after its confirmation."""

    def test_deleting_takes_the_item_and_its_votes(self):
        """Test the file: the item gone, its two votes gone, the third kept."""
        self.post("oil/delete")

        self.assertIsNone(self.stored_item("oil"))
        self.assertEqual([v["id"] for v in self.stored()["votes"]], ["v3"])

    def test_the_selection_moves_to_the_next_row(self):
        """Test the 303 onto the row that followed, with the view kept."""
        response = self.post("oil/delete", {"category": "Linear"})

        self.assertEqual(
            self.redirect_of(response)[1],
            {"selected": "alpaca", "done": "deleted", "item": "oil", "category": "Linear"},
        )

    def test_last_change_names_what_was_deleted(self):
        """Test the one sentence the project cannot supply, kept by the registry."""
        page = self.landed(self.post("oil/delete"))

        self.assertEqual(
            cell_text(page, "tb-last").rsplit(" · ", 1)[0],
            "Deleted (10) Gateron Oil King and its 2 votes",
        )

    def test_a_retired_item_can_be_deleted(self):
        """Test the one action both kinds of row share."""
        self.post("blue/delete", {"retired": "1"})

        self.assertIsNone(self.stored_item("blue"))

    def test_an_item_that_has_gone_changes_nothing(self):
        """Test the double submit."""
        self.post("oil/delete")
        before = self.snapshot()

        response = self.post("oil/delete")

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.redirect_of(response), (ITEMS_URL, {}))


def slot_error(body: str) -> str:
    """
    Read a refused slot's error the way a screen reader would.

    Args:
        body: The form fragment.

    Returns:
        str: The error's text, tags stripped and whitespace collapsed.
    """
    error = re.search(r'<p class="field-error" id="err-slot">(.*?)</p>', body, re.S).group(1)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", error))).strip()


class TestSlotConflictWords(ActionsTestCase):
    """
    Test cases for what a slot conflict offers instead, on every kind of board.

    Words, for once, because the three endings are three different pieces of
    advice and which one is drawn is decided by the project, not the template.
    """

    def test_a_board_with_free_slots_lists_them(self):
        """Test the mockup's sentence."""
        body = self.fragment("new?submitted=1&name=Holy+Panda&slot=10")

        self.assertEqual(
            slot_error(body), "Slot 10 is taken by Gateron Oil King; free: 2, Enter."
        )

    def test_a_full_board_says_none_are_free(self):
        """Test the ending when every slot on the list is held."""
        self.write(PROJECT, project_data(slots=["1", "10", "Apostrophe"], votes=VOTES))

        body = self.fragment("new?submitted=1&name=Holy+Panda&slot=10")

        self.assertEqual(slot_error(body), "Slot 10 is taken by Gateron Oil King; no slots are free.")

    def test_a_project_with_no_slot_list_says_identifiers_are_unique(self):
        """Test the ending with no board to offer a free slot from."""
        self.write(PROJECT, project_data(slots=[], slot_labels={}, votes=VOTES))

        body = self.fragment("new?submitted=1&name=Holy+Panda&slot=10")

        self.assertEqual(
            slot_error(body),
            "Slot 10 is taken by Gateron Oil King; identifiers are unique among active items.",
        )


class TestLastChange(ActionsTestCase):
    """
    Test cases for the Last change cell, which trusts nothing in the query.

    Its sentence and time are the registry's record of the project's last
    change, written only when the address names that change.
    """

    MODIFIED = "2026-09-16 21:04"

    # The cell when it writes no sentence: the modified time and nothing else.
    # After a mutation the modified time is today's, so it is matched by shape.
    TIME_ONLY = r"^\d{4}-\d\d-\d\d \d\d:\d\d$"

    def entry(self):
        """
        Reach the project's registry entry.

        Returns:
            OpenProject: The entry the routes share.
        """
        return self.app.state.registry.open(PROJECT)

    def test_an_address_with_no_change_behind_it_is_not_written(self):
        """
        Test that a done this server made no record of leaves the modified time.

        Including ones the project would bear out - oil exists, blue is
        retired - because nothing here says when they happened.
        """
        for query in ("done=edited&item=nope", "done=edited&item=oil",
                      "done=retired&item=blue", "done=deleted&item=oil",
                      "done=sideways&item=oil"):
            with self.subTest(query=query):
                self.assertEqual(cell_text(self.sheet(query), "tb-last"), self.MODIFIED)

    def test_each_kind_is_written_only_for_its_own_address(self):
        """
        Test every mutation's sentence against its address and two near misses.

        The address it landed on writes it; the same `done` about another item,
        and the same item under another `done`, write the modified time.
        """
        posts = {
            "added": ("new", {"name": "Holy Panda", "slot": "2"}, "Added (2) Holy Panda"),
            "edited": ("oil/edit", {"name": "Oil King", "slot": "10"}, "Edited (10) Oil King"),
            "replaced": (
                "oil/replace", {"name": "Oil King V2", "cat": "Linear", "slot": "10"},
                "Replaced Gateron Oil King with (10) Oil King V2",
            ),
            "reactivated": (
                "blue/reactivate", {"slot": "2", "retired": "1"},
                "Reactivated (2) Cherry MX Blue",
            ),
            "retired": ("oil/retire", {}, "Retired Gateron Oil King · slot 10 freed"),
            "deleted": ("oil/delete", {}, "Deleted (10) Gateron Oil King and its 2 votes"),
        }
        for kind, (path, data, sentence) in posts.items():
            with self.subTest(kind=kind):
                self.seed()
                self.app.state.registry.forget(PROJECT)
                response = self.post(path, data)
                query = self.redirect_of(response)[1]
                self.assertEqual(query["done"], kind)
                subject = query["item"]

                landed = cell_text(self.landed(response), "tb-last")
                self.assertEqual(landed.rsplit(" · ", 1)[0], sentence)

                other_kind = "edited" if kind != "edited" else "added"
                for miss in (f"done={kind}&item=brown", f"done={other_kind}&item={subject}"):
                    with self.subTest(miss=miss):
                        self.assertRegex(cell_text(self.sheet(miss), "tb-last"), self.TIME_ONLY)

    def test_a_deletion_is_named_only_for_the_item_deleted(self):
        """Test that the delete note is not read out for an item still there."""
        self.post("oil/delete")

        body = self.sheet("done=deleted&item=cream")

        self.assertRegex(cell_text(body, "tb-last"), self.TIME_ONLY)

    def test_an_older_change_is_not_relabelled_by_a_newer_one(self):
        """Test that only the last change is written, and a later one retires it."""
        retired = self.landed(self.post("oil/retire"))
        self.assertTrue(cell_text(retired, "tb-last").startswith("Retired Gateron Oil King"))

        self.post("jade/edit", {"name": "Box Jade", "slot": "2"})

        stale = self.sheet("selected=jade&done=retired&item=oil")
        self.assertRegex(cell_text(stale, "tb-last"), self.TIME_ONLY)
        current = self.sheet("selected=jade&done=edited&item=jade")
        self.assertTrue(cell_text(current, "tb-last").startswith("Edited (2) Box Jade · "))

    def test_the_time_is_the_change_s_own(self):
        """Test the recorded time, not the modified time a later write moves."""
        self.post("oil/retire")
        recorded = self.entry().last_change.time.strftime("%H:%M")
        # A vote, or the desktop saving, moves the modified time on.
        self.entry().session.project.modified = datetime(2031, 1, 2, 3, 4)

        body = self.sheet("done=retired&item=oil")

        self.assertEqual(cell_text(body, "tb-last").rsplit(" · ", 1)[1], recorded)

    def test_a_restart_forgets_the_change(self):
        """Test that a server with no record falls back to the modified time."""
        self.post("oil/retire")
        self.app.state.registry.forget(PROJECT)

        body = self.sheet("done=retired&item=oil")

        self.assertRegex(cell_text(body, "tb-last"), self.TIME_ONLY)

    def test_a_change_belongs_to_its_project(self):
        """Test that one project's record is not read out on another's sheet."""
        self.write("Other.pairrank", project_data(items=ITEMS))
        self.post("oil/delete")

        body = self.client.get("/projects/Other.pairrank/items?done=deleted&item=oil").text

        self.assertEqual(cell_text(body, "tb-last"), self.MODIFIED)

    def test_no_cookie_carries_the_change(self):
        """Test that the sentence needs nothing from the browser."""
        response = self.post("oil/delete")

        self.assertNotIn("set-cookie", response.headers)


class TestChangedOnDisk(ActionsTestCase):
    """Test cases for a mutation over a file that changed under the server."""

    def test_the_edit_lands_on_the_file_as_it_is_now(self):
        """
        Test that the mutation re-reads the file before changing it.

        The desktop app adds an item over SMB while the sheet is open; a retire
        from the web must keep it rather than write the stale copy back.
        """
        self.sheet()  # opened, and cached
        self.write(PROJECT, project_data(items=ITEMS + [item("new", "Desk Added")], votes=VOTES))

        self.post("oil/retire")

        self.assertIsNotNone(self.stored_item("new"))
        self.assertEqual(self.stored_item("oil")["status"], "retired")

    def test_the_page_it_lands_on_says_so_once(self):
        """Test that the reload notice is taken by the page after the 303, and only it."""
        self.sheet()
        self.write(PROJECT, project_data(items=ITEMS + [item("new", "Desk Added")], votes=VOTES))

        page = self.landed(self.post("oil/retire"))

        self.assertIn(RELOADED_NOTE, cell_text(page, "tb-last"))
        self.assertNotIn(RELOADED_NOTE, cell_text(self.sheet(), "tb-last"))

    def test_a_rows_swap_leaves_the_notice_for_a_page_that_shows_it(self):
        """Test that an htmx request, which drops the Last change cell, does not take it."""
        self.sheet()
        self.write(PROJECT, project_data(items=ITEMS + [item("new", "Desk Added")], votes=VOTES))
        response = self.post("oil/retire")

        self.client.get(ITEMS_URL, headers={"HX-Request": "true"})

        self.assertIn(RELOADED_NOTE, cell_text(self.landed(response), "tb-last"))


class TestAddCell(ActionsTestCase):
    """Test cases for the Add cell, which keeps the view."""

    def test_add_carries_the_filter(self):
        """Test the hidden fields of the Add cell on a filtered sheet."""
        body = self.sheet("q=cherry&retired=1")
        cell = re.search(r'<form class="tb-cell tb-press span-2" id="add-cell".*?</form>', body, re.S).group(0)

        self.assertIn('<input type="hidden" name="form" value="new">', cell)
        self.assertIn('<input type="hidden" name="q" value="cherry">', cell)
        self.assertIn('<input type="hidden" name="retired" value="1">', cell)


class TestActionsUnderARootPath(ActionsTestCase):
    """Test cases for the callouts and mutations behind a proxy on a subpath."""

    root_path = "/rank"
    prefixed = f"/rank{ITEMS_URL}"

    def test_a_callout_s_actions_carry_the_prefix(self):
        """Test every address the actions callout points at."""
        body = self.fragment("oil/callout")

        for verb in ("edit", "replace", "delete"):
            with self.subTest(verb=verb):
                self.assertIn(f'hx-get="{self.prefixed}/oil/{verb}"', body)
        self.assertIn(f'action="{self.prefixed}/oil/retire"', body)

    def test_a_form_posts_and_cancels_under_the_prefix(self):
        """Test the edit form's action and its Cancel."""
        body = self.fragment("oil/edit")

        self.assertIn(f'action="{self.prefixed}/oil/edit"', body)
        self.assertIn(f'href="{self.prefixed}?selected=oil"', element(body, r'<a class="cell-button"'))

    def test_a_mutation_lands_under_the_prefix(self):
        """Test the 303 of a change that went through."""
        path, query = self.redirect_of(self.post("oil/retire"))

        self.assertEqual(path, self.prefixed)
        self.assertEqual(query["done"], "retired")
        self.assertEqual(self.stored_item("oil")["status"], "retired")

    def test_a_refusal_lands_under_the_prefix(self):
        """Test the 303 back to the form with its draft."""
        path, query = self.redirect_of(self.post("new", {"name": ""}))

        self.assertEqual(path, self.prefixed)
        self.assertEqual(query["form"], "new")


if __name__ == "__main__":
    unittest.main()
