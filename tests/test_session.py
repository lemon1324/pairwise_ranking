"""Unit tests for the frontend-independent ProjectSession."""

import random
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.app.confidence import ConfidenceReading
from src.app.record import UNKNOWN_OPPONENT_NAME
from src.app.session import DuplicateTargetError, NoPairReason, ProjectSession
from src.data.project_storage import ProjectStorage
from src.models.export import EXPORT_HEADER, build_export_rows
from src.models.item import Item
from src.models.project import Project
from src.models.settings import Settings
from src.models.vote import Vote


# Fixed clock so decayed weights and timestamps are deterministic.
NOW = datetime(2026, 1, 1, 12, 0, 0)


def build_items(count: int, with_identifiers: bool = True) -> list[Item]:
    """
    Build a run of items with stable ids.

    Args:
        count: How many items to build.
        with_identifiers: Whether each item gets an identifier of its own.

    Returns:
        list[Item]: Items named "Item 0" upwards, with ids "item-0" upwards.
    """
    return [
        Item(
            name=f"Item {index}",
            description=f"Description {index}",
            identifier=f"A{index}" if with_identifiers else "",
            id=f"item-{index}",
        )
        for index in range(count)
    ]


def build_project(
    items: Optional[list[Item]] = None,
    votes: Optional[list[Vote]] = None,
    settings: Optional[Settings] = None,
    slots: Optional[list[str]] = None,
    slot_labels: Optional[dict[str, str]] = None,
    file_path: Optional[Path] = None,
) -> Project:
    """
    Build a project around the given items and votes.

    Args:
        items: The items to hold, or None for four items with identifiers.
        votes: The votes to hold, or None for none.
        settings: The settings to use, or None for the defaults.
        slots: The slot list, or None for no slots.
        slot_labels: The short label per slot, or None for none.
        file_path: The file to autosave to, or None for an unsaved project.

    Returns:
        Project: The constructed project.
    """
    return Project(
        name="Session Fixture",
        created=NOW,
        modified=NOW,
        items=build_items(4) if items is None else items,
        votes=list(votes or []),
        settings=settings if settings is not None else Settings(),
        slots=list(slots or []),
        slot_labels=dict(slot_labels or {}),
        file_path=file_path,
    )


def build_session(project: Optional[Project] = None, seed: Optional[int] = None,
                  **kwargs) -> ProjectSession:
    """
    Build a session over a project.

    Args:
        project: The project to wrap, or None for the default fixture.
        seed: Seed for a fresh random source per selection, or None to leave
            the session's own fresh-per-selection default in place.
        **kwargs: Further keyword arguments for the project fixture, used only
            when no project is given.

    Returns:
        ProjectSession: The constructed session.
    """
    if project is None:
        project = build_project(**kwargs)
    rng_factory = None if seed is None else (lambda: random.Random(seed))
    return ProjectSession(project, rng_factory=rng_factory)


def build_vote(winner_id: str, loser_id: str, weight: float = 1.0,
               days_ago: float = 0.0) -> Vote:
    """
    Build a vote at a fixed offset before the reference time.

    Args:
        winner_id: Id of the winning item.
        loser_id: Id of the losing item.
        weight: The vote weight.
        days_ago: How long before NOW the vote was cast.

    Returns:
        Vote: The constructed vote.
    """
    return Vote(
        winner_id=winner_id,
        loser_id=loser_id,
        weight=weight,
        timestamp=NOW - timedelta(days=days_ago),
    )


class TestProjectSessionRankings(unittest.TestCase):
    """Test cases for the memoised rankings."""

    def test_no_rankings_below_two_items(self):
        """Test that a project with one item ranks as None, not an empty list."""
        for count in (0, 1):
            with self.subTest(count=count):
                session = build_session(items=build_items(count))
                self.assertIsNone(session.rankings())

    def test_two_items_produce_rankings(self):
        """Test that two items are enough to fit the model."""
        session = build_session(items=build_items(2))

        rankings = session.rankings()

        self.assertIsNotNone(rankings)
        self.assertEqual(len(rankings), 2)

    def test_retired_items_are_ranked_by_the_model(self):
        """Test that retired items keep a rating and stay in the results."""
        items = build_items(3)
        items[2].retire()
        session = build_session(items=items)

        rankings = session.rankings()

        self.assertEqual({r.item.id for r in rankings}, {"item-0", "item-1", "item-2"})

    def test_only_active_items_are_numbered(self):
        """Test that retired items carry no rank while active ones count from 1."""
        items = build_items(3)
        items[1].retire()
        session = build_session(items=items)

        ranks = {r.item.id: r.rank for r in session.rankings()}

        self.assertIsNone(ranks["item-1"])
        self.assertEqual(sorted(r for r in ranks.values() if r is not None), [1, 2])

    def test_a_retired_item_does_not_change_the_other_ratings(self):
        """Test that ratings are computed over all items, retired included."""
        votes = [build_vote("item-0", "item-1", 2.0), build_vote("item-1", "item-2")]
        # Decay is measured against the wall clock, so it is switched off here
        # to keep the two fits comparable.
        settings = Settings(decay_timescale_days=0.0)
        active = build_session(
            project=build_project(items=build_items(3), votes=votes, settings=settings)
        )

        retired_items = build_items(3)
        retired_items[2].retire()
        retired = build_session(
            project=build_project(
                items=retired_items, votes=votes, settings=settings
            )
        )

        self.assertEqual(
            {r.item.id: r.strength for r in active.rankings()},
            {r.item.id: r.strength for r in retired.rankings()},
        )

    def test_rankings_are_memoised(self):
        """Test that reading the rankings twice returns the same objects."""
        session = build_session()

        self.assertIs(session.rankings(), session.rankings())

    def test_a_mutation_drops_the_memo(self):
        """Test that voting makes the next read recompute."""
        session = build_session()
        before = session.rankings()

        session.vote("item-0", "item-1", 2.0)

        self.assertIsNot(session.rankings(), before)


class TestProjectSessionConfidence(unittest.TestCase):
    """Test cases for the confidence reading the session exposes."""

    def test_no_reading_without_enough_items(self):
        """Test that a project with one item has no reading rather than an error."""
        session = build_session(items=build_items(1))

        self.assertIsNone(session.confidence())

    def test_no_reading_when_only_one_item_is_active(self):
        """Test that retired items do not make up a missing neighbour."""
        items = build_items(2)
        items[1].retire()
        session = build_session(items=items)

        self.assertIsNone(session.confidence())

    def test_reading_over_the_active_items(self):
        """Test that the reading counts one neighbour less than the active items."""
        session = build_session(
            items=build_items(4),
            votes=[
                build_vote("item-0", "item-1"),
                build_vote("item-1", "item-2"),
                build_vote("item-2", "item-3"),
            ],
        )

        reading = session.confidence()

        self.assertIsNotNone(reading)
        self.assertEqual(reading.neighbours, 3)
        self.assertLessEqual(reading.settled, reading.neighbours)

    def test_reading_follows_the_votes(self):
        """Test that casting votes changes the reading rather than caching it."""
        session = build_session(
            items=build_items(3),
            votes=[build_vote("item-0", "item-1")],
        )
        before = session.confidence()

        for _ in range(20):
            session.vote("item-0", "item-1", 3.0)
            session.vote("item-1", "item-2", 3.0)

        self.assertGreater(session.confidence().settled, before.settled)

    def test_the_reader_is_swappable(self):
        """Test that a session can be handed another confidence formula."""

        class Fixed:
            """A reader that always reports the same thing."""

            def read(self, rankings):
                """Return a fixed reading."""
                return ConfidenceReading(settled=2, neighbours=2, tolerance=9.0)

        session = ProjectSession(build_project(), confidence_reader=Fixed())

        self.assertEqual(session.confidence().tolerance, 9.0)

    def test_the_reader_is_asked_for_the_current_rankings(self):
        """Test that the session hands its rankings straight to the reader."""
        seen = []

        class Recording:
            """A reader that remembers what it was given."""

            def read(self, rankings):
                """Record the rankings and report nothing."""
                seen.append(rankings)
                return None

        session = ProjectSession(build_project(), confidence_reader=Recording())

        self.assertIsNone(session.confidence())
        self.assertEqual(seen, [session.rankings()])


class TestProjectSessionPairOffer(unittest.TestCase):
    """Test cases for choosing the next pair to compare."""

    def test_pair_is_offered_when_two_items_are_active(self):
        """Test that an ordinary project offers a pair with statistics."""
        session = build_session(seed=0, items=build_items(2))

        offer = session.next_pair()

        self.assertTrue(offer.has_pair)
        self.assertIsNone(offer.reason)
        self.assertEqual(offer.stats["total_items"], 2)
        self.assertFalse(offer.blinded)

    def test_too_few_items_has_the_plain_reason(self):
        """Test that a project with fewer than two active items says so."""
        for count in (0, 1):
            with self.subTest(count=count):
                session = build_session(items=build_items(count))

                offer = session.next_pair()

                self.assertFalse(offer.has_pair)
                self.assertEqual(offer.reason, NoPairReason.TOO_FEW_ITEMS)
                self.assertIsNone(offer.stats)

    def test_retired_items_are_never_offered(self):
        """Test that retiring an item takes it out of the eligible pool."""
        items = build_items(3)
        items[0].retire()
        session = build_session(seed=0, items=items)

        offer = session.next_pair()

        self.assertNotIn("item-0", {item.id for item in offer.pair})

    def test_retiring_down_to_one_item_leaves_no_pair(self):
        """Test that retired items do not count towards the two needed."""
        items = build_items(2)
        items[0].retire()
        session = build_session(items=items)

        offer = session.next_pair()

        self.assertEqual(offer.reason, NoPairReason.TOO_FEW_ITEMS)

    def test_blinded_mode_needs_two_identifiers(self):
        """Test that blinded mode reports its own reason when identifiers are missing."""
        items = build_items(3, with_identifiers=False)
        items[0].identifier = "A0"
        session = build_session(
            items=items, settings=Settings(blinded_comparison_mode=True)
        )

        offer = session.next_pair()

        self.assertEqual(offer.reason, NoPairReason.BLINDED_NO_IDENTIFIERS)
        self.assertTrue(offer.blinded)

    def test_blinded_mode_with_too_few_active_items_has_the_plain_reason(self):
        """Test that the blinded reason needs at least two active items."""
        session = build_session(
            items=build_items(1, with_identifiers=False),
            settings=Settings(blinded_comparison_mode=True),
        )

        offer = session.next_pair()

        self.assertEqual(offer.reason, NoPairReason.TOO_FEW_ITEMS)

    def test_blinded_mode_offers_identified_items_only(self):
        """Test that blinded mode compares the items that hold identifiers."""
        items = build_items(4, with_identifiers=False)
        items[1].identifier = "A1"
        items[3].identifier = "A3"
        session = build_session(
            seed=0, items=items, settings=Settings(blinded_comparison_mode=True)
        )

        offer = session.next_pair()

        self.assertEqual({item.id for item in offer.pair}, {"item-1", "item-3"})

    def test_seeded_selection_is_repeatable(self):
        """Test that a seeded random source makes the offer deterministic."""
        items = build_items(4)
        items[0].category = "Other"
        session = build_session(seed=7, items=items, settings=Settings())

        first = session.next_pair()
        second = session.next_pair()

        self.assertEqual(
            [item.id for item in first.pair], [item.id for item in second.pair]
        )

    def test_every_selection_builds_its_own_random_source(self):
        """Test that each selection gets a fresh selector and a fresh RNG."""
        built = []

        def rng_factory() -> random.Random:
            built.append(len(built))
            return random.Random(0)

        session = ProjectSession(build_project(), rng_factory=rng_factory)

        session.next_pair()
        session.next_pair()

        self.assertEqual(len(built), 2)

    def test_statistics_are_remembered_for_the_current_offer(self):
        """Test that the offer's statistics are also readable from the session."""
        session = build_session(seed=0)

        offer = session.next_pair()

        self.assertEqual(session.comparison_stats(), offer.stats)

    def test_statistics_cannot_be_written_through(self):
        """Test that the offer and the session each hand out their own copy."""
        session = build_session(seed=0)

        offer = session.next_pair()
        offer.stats["total_items"] = -1
        session.comparison_stats()["total_votes"] = -1

        self.assertEqual(session.comparison_stats()["total_items"], 4)
        self.assertEqual(session.comparison_stats()["total_votes"], 0)

    def test_statistics_are_cleared_when_no_pair_is_offered(self):
        """Test that a refused offer leaves no stale statistics behind."""
        session = build_session(seed=0, items=build_items(2))
        session.next_pair()

        session.project.items[0].retire()
        session.next_pair()

        self.assertIsNone(session.comparison_stats())

    def test_statistics_are_cleared_by_a_mutation(self):
        """Test that a mutation drops the statistics along with the rankings."""
        session = build_session(seed=0)
        session.next_pair()

        session.vote("item-0", "item-1", 2.0)

        self.assertIsNone(session.comparison_stats())


class TestProjectSessionVoting(unittest.TestCase):
    """Test cases for voting, skipping and undoing."""

    def setUp(self):
        """Set up test fixtures."""
        self.session = build_session(seed=0)

    def test_vote_records_the_comparison(self):
        """Test that a vote is appended to the project."""
        vote = self.session.vote("item-0", "item-1", 3.0)

        self.assertEqual(self.session.project.votes, [vote])
        self.assertEqual(vote.winner_id, "item-0")
        self.assertEqual(vote.loser_id, "item-1")
        self.assertEqual(vote.weight, 3.0)

    def test_vote_rejects_an_item_voting_against_itself(self):
        """Test that the model's own validation still applies."""
        with self.assertRaises(ValueError):
            self.session.vote("item-0", "item-0", 1.0)

    def test_skip_records_nothing(self):
        """Test that skipping leaves the votes alone and offers another pair."""
        offer = self.session.skip()

        self.assertEqual(self.session.project.votes, [])
        self.assertTrue(offer.has_pair)

    def test_undo_without_votes_returns_none(self):
        """Test that undoing with nothing to undo is a no-op."""
        self.assertIsNone(self.session.undo())

    def test_undo_removes_the_most_recent_vote(self):
        """Test that the newest vote is the one undone."""
        first = self.session.vote("item-0", "item-1", 1.0)
        second = self.session.vote("item-2", "item-3", 2.0)

        result = self.session.undo()

        self.assertIs(result.vote, second)
        self.assertEqual(self.session.project.votes, [first])

    def test_undo_re_offers_the_pair_with_the_winner_first(self):
        """Test that the undone vote's pair comes back, winner as the first item."""
        self.session.vote("item-2", "item-0", 2.0)

        result = self.session.undo()

        self.assertEqual([item.id for item in result.pair], ["item-2", "item-0"])

    def test_undo_reuses_the_statistics_of_the_fresh_offer(self):
        """Test that an undo selects exactly once and re-offers those statistics."""
        selections = []

        def rng_factory() -> random.Random:
            selections.append(len(selections))
            return random.Random(0)

        session = ProjectSession(build_project(), rng_factory=rng_factory)
        session.vote("item-0", "item-1", 2.0)
        selections.clear()

        result = session.undo()

        self.assertEqual(len(selections), 1)
        self.assertIsNotNone(result.pair)
        self.assertEqual(result.offer.stats, session.comparison_stats())

    def test_undo_still_offers_a_pair_of_its_own(self):
        """Test that the undo carries a fresh offer for the frontend to render."""
        self.session.vote("item-0", "item-1", 2.0)

        result = self.session.undo()

        self.assertTrue(result.offer.has_pair)

    def test_undo_of_the_only_vote_leaves_no_votes(self):
        """Test that undoing empties the project's votes when there was one."""
        self.session.vote("item-0", "item-1", 2.0)

        self.session.undo()

        self.assertEqual(self.session.project.votes, [])


class TestProjectSessionUndoEligibility(unittest.TestCase):
    """Test cases for undoing a vote whose items have since changed."""

    def setUp(self):
        """Set up test fixtures."""
        self.session = build_session(seed=0)

    def test_undo_does_not_re_offer_a_retired_item(self):
        """Test that a pair whose item was retired since cannot be put back."""
        self.session.vote("item-0", "item-1", 2.0)
        self.session.retire("item-1")

        result = self.session.undo()

        self.assertIsNone(result.pair)
        self.assertTrue(result.offer.has_pair)

    def test_deleting_an_item_takes_its_votes_with_it(self):
        """Test that a deleted item leaves no vote of its own to undo."""
        self.session.vote("item-0", "item-1", 2.0)

        self.session.delete_item("item-1")

        self.assertIsNone(self.session.undo())

    def test_undo_does_not_re_offer_an_item_the_project_has_lost(self):
        """Test that a vote naming an item that is gone cannot be put back."""
        # Deleting an item normally takes its votes with it, so a vote can only
        # outlive its item in a project file written elsewhere.
        project = build_project(votes=[build_vote("item-0", "item-gone", 2.0)])
        session = build_session(project=project, seed=0)

        result = session.undo()

        self.assertIsNotNone(result.vote)
        self.assertIsNone(result.pair)

    def test_undo_does_not_re_offer_an_item_without_an_identifier(self):
        """Test that blinded mode refuses a pair whose item lost its identifier."""
        session = build_session(seed=0, settings=Settings(blinded_comparison_mode=True))
        session.vote("item-0", "item-1", 2.0)
        session.update_item(Item(name="Item 1", identifier="", id="item-1"))

        result = session.undo()

        self.assertIsNone(result.pair)


class TestProjectSessionItemMutations(unittest.TestCase):
    """Test cases for adding, editing, retiring and deleting items."""

    def setUp(self):
        """Set up test fixtures."""
        self.session = build_session(seed=0)

    def test_add_item_appends_to_the_project(self):
        """Test that an added item joins the project."""
        item = Item(name="Item 4", identifier="A4", id="item-4")

        returned = self.session.add_item(item)

        self.assertIs(returned, item)
        self.assertIn(item, self.session.project.items)

    def test_add_item_invalidates_the_rankings(self):
        """Test that the rankings account for the new item."""
        before = len(self.session.rankings())

        self.session.add_item(Item(name="Item 4", id="item-4"))

        self.assertEqual(len(self.session.rankings()), before + 1)

    def test_update_item_replaces_it_in_place(self):
        """Test that an edited item keeps its position in the list."""
        edited = Item(name="Renamed", identifier="A1", id="item-1")

        returned = self.session.update_item(edited)

        self.assertIs(returned, edited)
        self.assertIs(self.session.project.items[1], edited)

    def test_update_of_an_unknown_id_is_a_silent_no_op(self):
        """Test that editing an item the project lost changes nothing and raises nothing."""
        before = list(self.session.project.items)

        returned = self.session.update_item(Item(name="Ghost", id="missing"))

        self.assertIsNone(returned)
        self.assertEqual(self.session.project.items, before)

    def test_retire_keeps_the_item_and_frees_its_identifier(self):
        """Test that retiring keeps the history but releases the slot."""
        retired = self.session.retire("item-1")

        self.assertFalse(retired.is_active())
        self.assertEqual(retired.identifier, "")
        self.assertIn(retired, self.session.project.items)

    def test_retire_of_an_unknown_id_is_tolerated(self):
        """Test that retiring a missing item returns None instead of raising."""
        self.assertIsNone(self.session.retire("missing"))

    def test_replace_hands_the_identifier_to_the_successor(self):
        """Test that the successor keeps the slot the predecessor held."""
        successor = Item(name="Item 1b", identifier="A1", id="item-1b")

        self.session.replace("item-1", successor)

        predecessor = self.session.project.find_item("item-1")
        self.assertEqual(predecessor.identifier, "")
        self.assertEqual(successor.identifier, "A1")
        self.assertEqual(self.session.taken_identifiers(), {"A0", "A1", "A2", "A3"})

    def test_replace_records_the_successor_on_the_predecessor(self):
        """Test that the retired item points at the item that took its place."""
        successor = Item(name="Item 1b", identifier="A1", id="item-1b")

        self.session.replace("item-1", successor)

        predecessor = self.session.project.find_item("item-1")
        self.assertFalse(predecessor.is_active())
        self.assertEqual(predecessor.replaced_by, "item-1b")

    def test_replace_of_an_unknown_id_still_adds_the_successor(self):
        """Test that a missing predecessor does not lose the new item."""
        successor = Item(name="Orphan", id="item-orphan")

        self.session.replace("missing", successor)

        self.assertIn(successor, self.session.project.items)

    def test_reactivate_returns_the_item_to_the_pool(self):
        """Test that a retired item becomes active again with a new identifier."""
        self.session.retire("item-1")

        reactivated = self.session.reactivate("item-1", "A9")

        self.assertTrue(reactivated.is_active())
        self.assertEqual(reactivated.identifier, "A9")
        self.assertIsNone(reactivated.replaced_by)

    def test_reactivate_without_an_identifier_leaves_it_empty(self):
        """Test that reactivating need not assign a slot."""
        self.session.retire("item-1")

        reactivated = self.session.reactivate("item-1")

        self.assertEqual(reactivated.identifier, "")

    def test_reactivate_of_an_unknown_id_is_tolerated(self):
        """Test that reactivating a missing item returns None instead of raising."""
        self.assertIsNone(self.session.reactivate("missing", "A9"))

    def test_delete_removes_the_item(self):
        """Test that a deleted item is gone from the project."""
        removed = self.session.delete_item("item-1")

        self.assertEqual(removed.id, "item-1")
        self.assertNotIn("item-1", {item.id for item in self.session.project.items})

    def test_delete_cascades_the_votes(self):
        """Test that every vote involving the deleted item goes with it."""
        self.session.vote("item-0", "item-1", 2.0)
        kept = self.session.vote("item-2", "item-3", 1.0)

        self.session.delete_item("item-1")

        self.assertEqual(self.session.project.votes, [kept])

    def test_delete_of_an_unknown_id_is_tolerated(self):
        """Test that deleting a missing item returns None instead of raising."""
        self.assertIsNone(self.session.delete_item("missing"))

    def test_delete_purges_votes_of_an_item_the_project_has_lost(self):
        """Test that the cascade runs even for an id no item holds any more."""
        session = build_session(
            project=build_project(votes=[build_vote("item-0", "item-gone", 2.0)])
        )

        session.delete_item("item-gone")

        self.assertEqual(session.project.votes, [])


class TestProjectSessionSlots(unittest.TestCase):
    """Test cases for the slot and identifier helpers."""

    def setUp(self):
        """Set up test fixtures."""
        items = build_items(2)
        self.session = build_session(
            items=items, slots=["A0", "A1", "A2", "A3"]
        )

    def test_free_slots_skips_the_occupied_ones(self):
        """Test that slots held by active items are not free."""
        self.assertEqual(self.session.free_slots(), ["A2", "A3"])

    def test_free_slots_can_release_one_item(self):
        """Test that excluding an item makes its own slot count as free."""
        self.assertEqual(
            self.session.free_slots(exclude_item_id="item-0"), ["A0", "A2", "A3"]
        )

    def test_free_slots_is_empty_without_a_slot_list(self):
        """Test that a project defining no slots has no free ones."""
        session = build_session(items=build_items(2))

        self.assertEqual(session.free_slots(), [])

    def test_retiring_frees_a_slot(self):
        """Test that a retired item releases the slot it held."""
        self.session.retire("item-0")

        self.assertEqual(self.session.free_slots(), ["A0", "A2", "A3"])

    def test_taken_identifiers_lists_active_holders(self):
        """Test that the identifiers in use come from the active items."""
        self.assertEqual(self.session.taken_identifiers(), {"A0", "A1"})

    def test_taken_identifiers_can_exclude_one_item(self):
        """Test that the item being edited does not block its own identifier."""
        self.assertEqual(
            self.session.taken_identifiers(exclude_item_id="item-1"), {"A0"}
        )

    def test_slot_summary_counts_use(self):
        """Test that the summary reports the totals and the free slots."""
        summary = self.session.slot_summary()

        self.assertEqual(summary.total, 4)
        self.assertEqual(summary.used, 2)
        self.assertEqual(summary.free, ["A2", "A3"])

    def test_slot_summary_cannot_be_written_through(self):
        """Test that editing a summary's free list leaves the project alone."""
        summary = self.session.slot_summary()

        summary.free.append("A9")

        self.assertEqual(self.session.slot_summary().free, ["A2", "A3"])

    def test_slot_summary_of_a_project_without_slots(self):
        """Test that a project defining no slots summarizes as empty."""
        summary = build_session(items=build_items(2)).slot_summary()

        self.assertEqual(summary.total, 0)
        self.assertEqual(summary.used, 0)
        self.assertEqual(summary.free, [])


class TestProjectSessionSettings(unittest.TestCase):
    """Test cases for applying and resetting settings."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.saves = []
        self.session = ProjectSession(
            build_project(
                slots=["A0", "A1"],
                file_path=Path(self.temp_dir) / "settings.pairrank",
            ),
            on_saved=self.saves.append,
        )

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_apply_settings_stores_the_settings(self):
        """Test that the entered settings replace the project's own."""
        self.session.apply_settings(Settings(weight_freshness=4.0), [])

        self.assertEqual(self.session.project.settings.weight_freshness, 4.0)

    def test_apply_settings_normalizes_the_raw_slot_list(self):
        """Test that the raw slot text is stripped, deduped and emptied of blanks."""
        stored = self.session.apply_settings(
            Settings(), ["  B1 ", "", "B2", "B1", "   "]
        )

        self.assertEqual(stored, ["B1", "B2"])
        self.assertEqual(self.session.project.slots, ["B1", "B2"])

    def test_apply_settings_saves_once(self):
        """Test that settings and slots together are exactly one save."""
        self.session.apply_settings(Settings(), ["B1"])

        self.assertEqual(len(self.saves), 1)

    def test_apply_settings_invalidates_the_rankings(self):
        """Test that a decay change is reflected in the next rankings."""
        before = self.session.rankings()

        self.session.apply_settings(Settings(decay_timescale_days=1.0), [])

        self.assertIsNot(self.session.rankings(), before)

    def test_reset_settings_restores_the_defaults(self):
        """Test that reset returns every algorithm setting to its default."""
        self.session.apply_settings(
            Settings(weight_freshness=4.0, blinded_comparison_mode=True), []
        )

        restored = self.session.reset_settings()

        self.assertEqual(restored, Settings())
        self.assertEqual(self.session.project.settings, Settings())

    def test_reset_settings_leaves_the_slots_alone(self):
        """Test that the slot list describes the project, not the algorithm."""
        self.session.apply_settings(Settings(), ["B1", "B2"])

        self.session.reset_settings()

        self.assertEqual(self.session.project.slots, ["B1", "B2"])


class TestProjectSessionSlotLabels(unittest.TestCase):
    """Test cases for the slot labels surviving a frontend that cannot edit them."""

    def setUp(self):
        """Set up a session whose project carries two labelled slots."""
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = Path(self.temp_dir) / "labels.pairrank"
        self.session = ProjectSession(
            build_project(
                slots=["Apostrophe", "Apex"],
                slot_labels={"Apostrophe": "'", "Apex": "Ax"},
                file_path=self.file_path,
            )
        )

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_apply_settings_preserves_the_labels(self):
        """Test that saving settings without touching the slots keeps the labels."""
        self.session.apply_settings(
            Settings(weight_freshness=4.0), ["Apostrophe", "Apex"]
        )

        self.assertEqual(
            self.session.project.slot_labels,
            {"Apostrophe": "'", "Apex": "Ax"},
        )

    def test_labels_survive_a_round_trip_through_the_file(self):
        """Test that a save and reload brings the labels back."""
        self.session.apply_settings(Settings(), ["Apostrophe", "Apex"])

        reloaded = ProjectStorage.load(self.file_path)

        self.assertEqual(
            reloaded.slot_labels, {"Apostrophe": "'", "Apex": "Ax"}
        )

    def test_reordering_the_slots_preserves_the_labels(self):
        """Test that moving a slot along the line does not lose its label."""
        self.session.apply_settings(Settings(), ["Apex", "Apostrophe"])

        self.assertEqual(
            self.session.project.slot_labels, {"Apex": "Ax", "Apostrophe": "'"}
        )

    def test_renaming_a_slot_drops_only_that_slots_label(self):
        """Test that a renamed slot loses its label and the others keep theirs."""
        self.session.apply_settings(Settings(), ["Apostrophe", "Apogee"])

        self.assertEqual(self.session.project.slots, ["Apostrophe", "Apogee"])
        self.assertEqual(self.session.project.slot_labels, {"Apostrophe": "'"})

    def test_dropping_every_slot_drops_every_label(self):
        """Test that clearing the slot line leaves no orphaned labels behind."""
        self.session.apply_settings(Settings(), [])

        self.assertEqual(self.session.project.slot_labels, {})

    def test_duplicating_carries_the_labels(self):
        """Test that a vote-free copy keeps the labels along with the slots."""
        copy_path = Path(self.temp_dir) / "copy.pairrank"

        copy = self.session.duplicate_without_votes("Copy", copy_path)

        self.assertEqual(
            copy.slot_labels, {"Apostrophe": "'", "Apex": "Ax"}
        )


class TestProjectSessionRename(unittest.TestCase):
    """Test cases for renaming the project."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = Path(self.temp_dir) / "rename.pairrank"
        self.session = build_session(project=build_project(file_path=self.file_path))

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rename_changes_the_name(self):
        """Test that the project takes the new name, stripped."""
        stored = self.session.rename("  Renamed  ")

        self.assertEqual(stored, "Renamed")
        self.assertEqual(self.session.project.name, "Renamed")

    def test_rename_rejects_an_empty_name(self):
        """Test that a blank name is refused by the model's own rule."""
        with self.assertRaises(ValueError):
            self.session.rename("   ")

    def test_rename_keeps_the_file_path(self):
        """Test that renaming does not move the project to another file."""
        self.session.rename("Renamed")

        self.assertEqual(self.session.project.file_path, self.file_path)
        self.assertEqual(ProjectStorage.load(self.file_path).name, "Renamed")


class TestProjectSessionExport(unittest.TestCase):
    """Test cases for the export rows."""

    #: (description, category, include_retired)
    FILTERS = [
        ("all", None, False),
        ("all_with_retired", None, True),
        ("linear", "Linear", False),
        ("linear_with_retired", "Linear", True),
        ("clicky", "Clicky", False),
        ("clicky_with_retired", "Clicky", True),
        ("unknown_category", "Nonexistent", False),
        ("unknown_category_with_retired", "Nonexistent", True),
    ]

    def setUp(self):
        """Build a project with two categories and a retired item."""
        items = build_items(4)
        items[0].category = "Linear"
        items[1].category = "Linear"
        items[2].category = "Clicky"
        items[3].category = "Clicky"
        items[3].retire()
        votes = [build_vote("item-0", "item-1", 2.0), build_vote("item-2", "item-0")]
        self.session = build_session(project=build_project(items=items, votes=votes))

    def test_export_rows_match_the_shared_builder(self):
        """Test that the session exports exactly what build_export_rows builds."""
        for label, category, include_retired in self.FILTERS:
            with self.subTest(label):
                self.assertEqual(
                    self.session.export_rows(category, include_retired),
                    build_export_rows(
                        self.session.rankings(),
                        include_retired=include_retired,
                        category=category,
                    ),
                )

    def test_export_of_an_unrankable_project_is_the_header_alone(self):
        """Test that a project with nothing to rank still exports its header."""
        session = build_session(items=build_items(1))

        self.assertEqual(session.export_rows(), [list(EXPORT_HEADER)])


class TestProjectSessionItemDetails(unittest.TestCase):
    """Test cases for the per-opponent weighted record."""

    def setUp(self):
        """Build a project whose items include two sharing a name."""
        items = build_items(3)
        items[1].name = "Twin"
        items[2].name = "Twin"
        votes = [
            build_vote("item-0", "item-1", 2.0, days_ago=30.0),
            build_vote("item-0", "item-2", 3.0),
            build_vote("item-1", "item-0", 1.0, days_ago=30.0),
        ]
        self.session = build_session(
            project=build_project(
                items=items, votes=votes, settings=Settings(decay_timescale_days=30.0)
            )
        )

    def test_same_named_opponents_stay_separate(self):
        """Test that the record keys by opponent id, not by name."""
        record = self.session.item_details("item-0", reference_time=NOW)

        self.assertEqual([r.opponent_id for r in record.wins], ["item-1", "item-2"])
        self.assertEqual([r.name for r in record.wins], ["Twin", "Twin"])

    def test_raw_and_decayed_weights_are_both_reported(self):
        """Test that the project's decay half-life is applied to the decayed weight."""
        record = self.session.item_details("item-0", reference_time=NOW)

        by_id = {r.opponent_id: r for r in record.wins}
        self.assertEqual(by_id["item-1"].weight_raw, 2.0)
        self.assertAlmostEqual(by_id["item-1"].weight_decayed, 1.0)
        self.assertEqual(by_id["item-2"].weight_raw, 3.0)
        self.assertAlmostEqual(by_id["item-2"].weight_decayed, 3.0)

    def test_losses_are_reported_too(self):
        """Test that the item's defeats land in the losses list."""
        record = self.session.item_details("item-0", reference_time=NOW)

        self.assertEqual([r.opponent_id for r in record.losses], ["item-1"])
        self.assertEqual(record.losses[0].weight_raw, 1.0)

    def test_an_item_with_no_votes_has_an_empty_record(self):
        """Test that an uncompared item reports no wins and no losses."""
        self.session.add_item(Item(name="Fresh", id="item-fresh"))

        record = self.session.item_details("item-fresh", reference_time=NOW)

        self.assertEqual(record.wins, [])
        self.assertEqual(record.losses, [])

    def test_an_opponent_the_project_lost_is_named_unknown(self):
        """Test that a vote naming a missing item still reports a record."""
        project = build_project(votes=[build_vote("item-0", "item-gone", 2.0)])
        session = build_session(project=project)

        record = session.item_details("item-0", reference_time=NOW)

        self.assertEqual(record.wins[0].opponent_id, "item-gone")
        self.assertEqual(record.wins[0].name, UNKNOWN_OPPONENT_NAME)


class TestProjectSessionPersistence(unittest.TestCase):
    """Test cases for autosaving and duplicating."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = Path(self.temp_dir) / "session.pairrank"
        self.copy_path = Path(self.temp_dir) / "copy.pairrank"
        self.saved = []
        self.session = ProjectSession(
            build_project(file_path=self.file_path),
            on_saved=self.saved.append,
        )

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_a_mutation_writes_the_file(self):
        """Test that voting saves the project without being asked."""
        self.session.vote("item-0", "item-1", 2.0)

        reloaded = ProjectStorage.load(self.file_path)
        self.assertEqual(len(reloaded.votes), 1)

    def test_every_mutation_reports_the_save(self):
        """Test that the on_saved callback fires once per mutation."""
        self.session.vote("item-0", "item-1", 2.0)
        self.session.retire("item-2")

        self.assertEqual(len(self.saved), 2)
        self.assertEqual(self.saved[0], self.session.project)

    def test_a_project_without_a_file_is_not_written(self):
        """Test that an unsaved project can be edited without raising."""
        session = ProjectSession(build_project(), on_saved=self.saved.append)

        session.vote("item-0", "item-1", 2.0)

        self.assertEqual(self.saved, [])
        self.assertEqual(len(session.project.votes), 1)

    def test_save_writes_on_demand(self):
        """Test that an explicit save writes the file the project points at."""
        session = ProjectSession(build_project(), on_saved=self.saved.append)
        session.project.file_path = self.file_path

        session.save()

        self.assertTrue(self.file_path.exists())
        self.assertEqual(len(self.saved), 1)

    def test_duplicate_without_votes_writes_a_vote_free_copy(self):
        """Test that the copy carries the items but none of the votes."""
        self.session.vote("item-0", "item-1", 2.0)

        copy = self.session.duplicate_without_votes("Copy", self.copy_path)

        self.assertEqual(copy.name, "Copy")
        self.assertEqual(copy.votes, [])
        self.assertEqual(len(copy.items), 4)
        self.assertTrue(self.copy_path.exists())

    def test_duplicate_leaves_the_source_alone(self):
        """Test that duplicating does not disturb the project being copied."""
        self.session.vote("item-0", "item-1", 2.0)

        self.session.duplicate_without_votes("Copy", self.copy_path)

        self.assertEqual(self.session.project.file_path, self.file_path)
        self.assertEqual(len(ProjectStorage.load(self.file_path).votes), 1)

    def test_duplicate_refuses_the_source_file(self):
        """Test that a copy cannot be written over the project it came from."""
        with self.assertRaises(DuplicateTargetError):
            self.session.duplicate_without_votes("Copy", self.file_path)

    def test_duplicate_refuses_the_source_file_by_another_route(self):
        """Test that the refusal compares resolved paths, not spelling."""
        indirect = Path(self.temp_dir) / "sub" / ".." / "session.pairrank"

        with self.assertRaises(DuplicateTargetError):
            self.session.duplicate_without_votes("Copy", indirect)

    def test_duplicate_of_an_unsaved_project_is_allowed(self):
        """Test that a project with no file of its own has nothing to overwrite."""
        session = ProjectSession(build_project())

        copy = session.duplicate_without_votes("Copy", self.copy_path)

        self.assertEqual(copy.name, "Copy")


if __name__ == "__main__":
    unittest.main()
