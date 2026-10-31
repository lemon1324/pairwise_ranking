"""Row building for CSV export of ranking results.

This module is deliberately free of Qt and of any file handling so the exported
layout can be tested directly. The UI decides where the rows go and writes them
with :class:`csv.writer`, which takes care of quoting.
"""

from typing import Optional

from src.models.ranking import (
    RankingResult,
    rating_points_per_log_unit,
    se_in_rating_points,
)


# Column headers of an exported rankings file, in order. The uncertainty is in
# rating points, the units of the rating beside it and of the +/- on the
# Rankings sheet; the raw Bradley-Terry standard error follows it under its own
# name.
EXPORT_HEADER = [
    "Rank",
    "Name",
    "Category",
    "Identifier",
    "Status",
    "ELO Rating",
    "Uncertainty (± rating)",
    "Log-strength SE",
    "Comparisons",
    "Description",
]

# Suffix of an export's default file name, after the project's file stem.
EXPORT_SUFFIX = "rankings.csv"


def build_export_rows(
    rankings: list[RankingResult],
    include_retired: bool,
    category: Optional[str],
) -> list[list[str]]:
    """
    Build the rows of a rankings CSV export.

    Args:
        rankings: The ranking results to export, in display order.
        include_retired: Whether retired items are included. When False, only
            active items are exported.
        category: Category to restrict the export to, or None for every
            category.

    Returns:
        list[list[str]]: The header row followed by one row per exported
        result. Every cell is a string; the rank cell is empty for items that
        carry no rank (retired items), and the rating-point uncertainty is
        empty when the ratings carry no spread to measure it on.
    """
    rows: list[list[str]] = [list(EXPORT_HEADER)]
    # Over every result, before any filtering: the ratings are z-scores across
    # everything the model was given.
    scale = rating_points_per_log_unit(rankings)

    for result in rankings:
        item = result.item
        is_active = item.is_active()

        if not include_retired and not is_active:
            continue
        if category is not None and item.category != category:
            continue

        se_points = se_in_rating_points(result, scale)
        rows.append([
            "" if result.rank is None else str(result.rank),
            item.name,
            item.category,
            item.identifier,
            item.status,
            f"{result.elo_rating:.0f}",
            "" if se_points is None else str(se_points),
            f"{result.log_strength_se:.4f}",
            str(result.comparison_count),
            item.description,
        ])

    return rows
