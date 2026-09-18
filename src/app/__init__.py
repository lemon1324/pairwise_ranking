"""Frontend-independent application services for the pairwise ranking app.

Nothing in this package may import PyQt6. The desktop UI in :mod:`src.ui` and
the planned web UI are both meant to be thin callers of the code here, so every
dialog, message box and widget stays on the frontend side of the line.
"""

from .confidence import (
    AdjacentNeighbourConfidence,
    ConfidenceReader,
    ConfidenceReading,
    DEFAULT_CONFIDENCE_READER,
)
from .items import (
    FIELD_IDENTIFIER,
    FIELD_NAME,
    ItemFieldError,
    ItemForm,
    ItemFormVerdict,
    validate_item_form,
)
from .record import (
    UNKNOWN_OPPONENT_NAME,
    OpponentRecord,
    WeightedRecord,
    weighted_record,
)
from .register import (
    MAX_FILE_STEM_LENGTH,
    ProjectCondition,
    ProjectFileInfo,
    duplicate_project_file,
    import_file,
    probe_project_file,
    resolve_project_path,
    scan_directory,
    unique_file_name,
)
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
    "AdjacentNeighbourConfidence",
    "ConfidenceReader",
    "ConfidenceReading",
    "DEFAULT_CONFIDENCE_READER",
    "FIELD_IDENTIFIER",
    "FIELD_NAME",
    "ItemFieldError",
    "ItemForm",
    "ItemFormVerdict",
    "validate_item_form",
    "UNKNOWN_OPPONENT_NAME",
    "OpponentRecord",
    "WeightedRecord",
    "weighted_record",
    "MAX_FILE_STEM_LENGTH",
    "ProjectCondition",
    "ProjectFileInfo",
    "duplicate_project_file",
    "import_file",
    "probe_project_file",
    "resolve_project_path",
    "scan_directory",
    "unique_file_name",
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
