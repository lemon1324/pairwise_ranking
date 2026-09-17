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
from .slots import (
    SlotLabelError,
    SlotLabelVerdict,
    clean_slot_labels,
    format_slot_list,
    label_collisions,
    parse_slot_list,
    short_label,
    validate_slot_labels,
)
from .session import (
    DuplicateTargetError,
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
    "SlotLabelError",
    "SlotLabelVerdict",
    "clean_slot_labels",
    "format_slot_list",
    "label_collisions",
    "parse_slot_list",
    "short_label",
    "validate_slot_labels",
    "DuplicateTargetError",
    "NoPairReason",
    "PairOffer",
    "ProjectSession",
    "SlotSummary",
    "UndoResult",
]
