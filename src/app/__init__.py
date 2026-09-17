"""Frontend-independent application services for the pairwise ranking app.

Nothing in this package may import PyQt6. The desktop UI in :mod:`src.ui` and
the planned web UI are both meant to be thin callers of the code here, so every
dialog, message box and widget stays on the frontend side of the line.
"""

from .items import (
    ItemFieldError,
    ItemForm,
    ItemFormVerdict,
    validate_item_form,
)
from .record import OpponentRecord, WeightedRecord, weighted_record
from .session import (
    NoPairReason,
    PairOffer,
    ProjectSession,
    SlotSummary,
    UndoResult,
)

__all__ = [
    "ItemFieldError",
    "ItemForm",
    "ItemFormVerdict",
    "validate_item_form",
    "OpponentRecord",
    "WeightedRecord",
    "weighted_record",
    "NoPairReason",
    "PairOffer",
    "ProjectSession",
    "SlotSummary",
    "UndoResult",
]
