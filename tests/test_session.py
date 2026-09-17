"""Unit tests for the frontend-independent ProjectSession."""

import random
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.app.session import NoPairReason, ProjectSession
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
    file_path: Optional[Path] = None,
) -> Project:
    """
    Build a project around the given items and votes.

    Args:
        items: The items to hold, or None for four items with identifiers.
        votes: The votes to hold, or None for none.
        settings: The settings to use, or None for the defaults.
        slots: The slot list, or None for no slots.
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


class TestProjectSessionPairOffer(unittest.TestCase):
    """Test cases for choosing the next pair to compare."""

    def test_pair_is_offered_when_two_items_are_active(self):
        """Test that an ordinary project offers a pair with statistics."""
        session = build_session(seed=0, items=build_items(2))

        offer = session.next_pair()

        self.assertTrue(offer.has_pair())
        self.assertIsNone(offer.reason)
        self.assertEqual(offer.stats["total_items"], 2)
        self.assertFalse(offer.blinded)

    def test_too_few_items_has_the_plain_reason(self):
        """Test that a project with fewer than two active items says so."""
        for count in (0, 1):
            with self.subTest(count=count):
                session = build_session(items=build_items(count))

                offer = session.next_pair()

                self.assertFalse(offer.has_pair())
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

        self.assertIs(session.comparison_stats(), offer.stats)

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
        self.assertTrue(offer.has_pair())

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
        """Test that the re-offered pair carries the statistics just computed."""
        self.session.vote("item-0", "item-1", 2.0)

        result = self.session.undo()

        self.assertIsNotNone(result.pair)
        self.assertIs(result.offer.stats, self.session.comparison_stats())

    def test_undo_still_offers_a_pair_of_its_own(self):
        """Test that the undo carries a fresh offer for the frontend to render."""
        self.session.vote("item-0", "item-1", 2.0)

        result = self.session.undo()

        self.assertTrue(result.offer.has_pair())

    def test_undo_of_the_only_vote_leaves_no_votes(self):
        """Test that undoing empties the project's votes when there was one."""
        self.session.vote("item-0", "item-1", 2.0)

        self.session.undo()

        self.assertEqual(self.session.project.votes, [])


if __name__ == "__main__":
    unittest.main()
