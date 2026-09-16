"""Unit tests for CSV export row building."""

import csv
import io
import unittest

from src.models.export import EXPORT_HEADER, build_export_rows
from src.models.item import Item
from src.models.ranking import RankingResult


def _result(
    item: Item,
    rank=None,
    elo_rating: float = 1500.0,
    log_strength_se: float = 0.0,
    comparison_count: int = 0,
) -> RankingResult:
    """
    Build a RankingResult for the given item with plausible defaults.

    Args:
        item: The ranked item.
        rank: The rank to record, or None for an unranked item.
        elo_rating: The ELO rating to record.
        log_strength_se: The standard error to record.
        comparison_count: The comparison count to record.

    Returns:
        RankingResult: The constructed result.
    """
    return RankingResult(
        item=item,
        strength=1.0,
        log_strength=0.0,
        elo_rating=elo_rating,
        rank=rank,
        comparison_count=comparison_count,
        log_strength_se=log_strength_se,
    )


class TestBuildExportRowsHeader(unittest.TestCase):
    """Test cases for the exported header row."""

    def test_header_is_first_row(self):
        """Test that the header row comes first and has the expected columns."""
        rows = build_export_rows([], include_retired=True, category=None)

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            [
                "Rank",
                "Name",
                "Category",
                "Identifier",
                "Status",
                "ELO Rating",
                "Uncertainty (SE)",
                "Comparisons",
                "Description",
            ],
        )

    def test_header_constant_matches(self):
        """Test that the module constant is what gets written."""
        rows = build_export_rows([], include_retired=False, category=None)
        self.assertEqual(rows[0], EXPORT_HEADER)

    def test_header_is_a_copy(self):
        """Test that mutating a returned row does not corrupt the constant."""
        rows = build_export_rows([], include_retired=False, category=None)
        rows[0][0] = "Mutated"
        self.assertEqual(EXPORT_HEADER[0], "Rank")


class TestBuildExportRowsContent(unittest.TestCase):
    """Test cases for the exported data rows."""

    def test_row_cells(self):
        """Test that every column is rendered with the expected formatting."""
        item = Item(
            name="Alpha",
            description="First item",
            identifier="A1",
            category="Linear",
            id="alpha",
        )
        rows = build_export_rows(
            [_result(item, rank=1, elo_rating=1612.6, log_strength_se=0.123456,
                     comparison_count=7)],
            include_retired=False,
            category=None,
        )

        self.assertEqual(
            rows[1],
            ["1", "Alpha", "Linear", "A1", "active", "1613", "0.1235", "7", "First item"],
        )

    def test_all_cells_are_strings(self):
        """Test that rows contain only strings, as csv.writer expects text."""
        item = Item(name="Alpha", id="alpha")
        rows = build_export_rows(
            [_result(item, rank=1)], include_retired=False, category=None
        )
        for row in rows:
            for cell in row:
                self.assertIsInstance(cell, str)

    def test_order_follows_input(self):
        """Test that rows are emitted in the order the rankings were given."""
        first = Item(name="First", id="first")
        second = Item(name="Second", id="second")
        rows = build_export_rows(
            [_result(first, rank=1), _result(second, rank=2)],
            include_retired=False,
            category=None,
        )
        self.assertEqual([row[1] for row in rows[1:]], ["First", "Second"])


class TestBuildExportRowsRetired(unittest.TestCase):
    """Test cases for the include_retired flag."""

    def setUp(self):
        """Build one active and one retired result."""
        self.active = Item(name="Active", identifier="1", id="active-id")
        self.retired = Item(name="Retired", identifier="2", id="retired-id")
        self.retired.retire()
        self.rankings = [
            _result(self.active, rank=1),
            _result(self.retired, rank=None),
        ]

    def test_exclude_retired_drops_rows(self):
        """Test that retired items are dropped when they are not included."""
        rows = build_export_rows(self.rankings, include_retired=False, category=None)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "Active")

    def test_include_retired_keeps_rows(self):
        """Test that retired items are kept when they are included."""
        rows = build_export_rows(self.rankings, include_retired=True, category=None)

        self.assertEqual(len(rows), 3)
        self.assertEqual([row[1] for row in rows[1:]], ["Active", "Retired"])

    def test_retired_row_has_blank_rank(self):
        """Test that a retired item exports an empty rank cell."""
        rows = build_export_rows(self.rankings, include_retired=True, category=None)

        self.assertEqual(rows[1][0], "1")
        self.assertEqual(rows[2][0], "")

    def test_retired_row_reports_status_and_empty_identifier(self):
        """Test that a retired row shows the retired status and freed slot."""
        rows = build_export_rows(self.rankings, include_retired=True, category=None)

        self.assertEqual(rows[2][3], "")
        self.assertEqual(rows[2][4], "retired")


class TestBuildExportRowsCategory(unittest.TestCase):
    """Test cases for the category filter."""

    def setUp(self):
        """Build results spread over two categories."""
        self.linear = Item(name="Linear one", category="Linear", id="lin")
        self.tactile = Item(name="Tactile one", category="Tactile", id="tac")
        self.rankings = [_result(self.linear, rank=1), _result(self.tactile, rank=2)]

    def test_none_category_keeps_everything(self):
        """Test that a None category applies no filter."""
        rows = build_export_rows(self.rankings, include_retired=True, category=None)
        self.assertEqual([row[2] for row in rows[1:]], ["Linear", "Tactile"])

    def test_category_filter_selects_one_category(self):
        """Test that only the named category is exported."""
        rows = build_export_rows(
            self.rankings, include_retired=True, category="Tactile"
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "Tactile one")

    def test_unknown_category_yields_header_only(self):
        """Test that a category nothing matches exports just the header."""
        rows = build_export_rows(
            self.rankings, include_retired=True, category="Clicky"
        )
        self.assertEqual(rows, [EXPORT_HEADER])

    def test_category_and_retired_filters_combine(self):
        """Test that the two filters are applied together."""
        retired = Item(name="Old linear", category="Linear", id="old")
        retired.retire()
        rankings = self.rankings + [_result(retired, rank=None)]

        rows = build_export_rows(rankings, include_retired=False, category="Linear")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "Linear one")


class TestBuildExportRowsCsvRoundTrip(unittest.TestCase):
    """Test cases for writing the rows through csv.writer."""

    @staticmethod
    def _round_trip(rows: list[list[str]]) -> list[list[str]]:
        """
        Write rows with csv.writer and read them back with csv.reader.

        Args:
            rows: The rows to write.

        Returns:
            list[list[str]]: The rows as parsed back from the CSV text.
        """
        buffer = io.StringIO(newline="")
        csv.writer(buffer).writerows(rows)
        return list(csv.reader(io.StringIO(buffer.getvalue(), newline="")))

    def test_quotes_and_commas_survive(self):
        """Test that a name with a quote and a comma round-trips intact."""
        tricky = 'The "Best", by far'
        item = Item(
            name=tricky,
            description='Notes: a "quoted" phrase, and a comma',
            identifier="A,1",
            category="Odd, Category",
            id="tricky",
        )

        rows = build_export_rows(
            [_result(item, rank=1)], include_retired=False, category=None
        )
        parsed = self._round_trip(rows)

        self.assertEqual(parsed[0], EXPORT_HEADER)
        self.assertEqual(parsed[1], rows[1])
        self.assertEqual(parsed[1][1], tricky)
        self.assertEqual(parsed[1][2], "Odd, Category")
        self.assertEqual(parsed[1][3], "A,1")

    def test_quoting_is_applied_in_the_text(self):
        """Test that the written text escapes quotes the way CSV requires."""
        item = Item(name='Say "hi", please', id="q")
        rows = build_export_rows(
            [_result(item, rank=1)], include_retired=False, category=None
        )

        buffer = io.StringIO(newline="")
        csv.writer(buffer).writerows(rows)
        text = buffer.getvalue()

        self.assertIn('"Say ""hi"", please"', text)

    def test_blank_rank_round_trips_as_empty_cell(self):
        """Test that a retired item's blank rank survives the CSV round trip."""
        retired = Item(name="Retired", id="retired-id")
        retired.retire()

        rows = build_export_rows(
            [_result(retired, rank=None)], include_retired=True, category=None
        )
        parsed = self._round_trip(rows)

        self.assertEqual(parsed[1][0], "")


if __name__ == "__main__":
    unittest.main()
