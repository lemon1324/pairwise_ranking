"""The drawing register: what is in the project directory, without opening it.

The register is the project picker's data layer. It lists one row per
``.pairrank`` file in the data directory - number, project name, item count,
vote count, when it was last written - and tags the files that are not in the
format this code writes.

**Listing must never change a file.**
:meth:`~src.data.project_storage.ProjectStorage.load` upgrades an old file in
place as a side effect: it writes a ``.pairrank.v<old>.bak`` beside it and
re-saves it in the current format. That is exactly right when a user opens a
project, and quite wrong when the register merely lists a directory - opening
the picker would silently rewrite every old file in it and scatter backups.
So the register reads files with :func:`probe_project_file`, which parses the
JSON and pulls out the handful of keys a row needs without ever constructing a
:class:`~src.models.project.Project` and without writing anything at all.

The probe is deliberately shallow. It checks the **top level** of the file -
the name, the two entry lists, the settings, the slots and the slot labels -
the same way :meth:`~src.models.project.Project.from_dict` checks it, and
stops there. It does not build the items and votes, because a row only needs
to count them, and so it cannot see the faults that only a full construction
would find: an item entry missing a required key, or a timestamp that is not a
date. An OK row therefore means "shaped like a project", which is a little
short of "will open". Chasing the rest would mean building the project the
probe exists not to build, and the cases it misses are rare enough that a
failed Open is the better place to meet them.

Projects are addressed by **file name within the data directory**, never by
arbitrary path. :func:`import_file` refuses a name carrying a path separator or
a parent reference, so a name arriving from a browser cannot reach outside the
directory it belongs in.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from itertools import count
from pathlib import Path
from typing import Optional

from src.data.format_version import CURRENT_FORMAT_VERSION, detect_version
from src.data.project_storage import (
    ProjectStorage,
    ensure_pairrank_suffix,
    safe_project_filename,
)
from src.models.project import Project


# File stem used when a project name sanitizes away to nothing.
DEFAULT_FILE_STEM = "Project"

# Longest file stem the register will build. ``safe_project_filename`` caps
# nothing, and a project name is free text, so the cap belongs here - a name
# long enough to blow past the filesystem's limit would otherwise fail at the
# write rather than at the naming.
#
# The cap counts **characters, not bytes**, which is far enough under the usual
# 255-byte NAME_MAX for any realistic name. The exception is a name of 64
# astral-plane characters, which encodes to 256 UTF-8 bytes and would raise at
# the write instead of being capped here. Byte-aware truncation is not worth
# the complication for a project name.
MAX_FILE_STEM_LENGTH = 64

# Separator between the two parts of a collision-suffixed file stem, as in
# "Tasting (2)".
_COLLISION_SUFFIX = " ({n})"


class ProjectCondition(Enum):
    """
    The condition a project file is in, as the register tags it.

    These are exactly the states the picker draws, no more: a file is either
    fine, or it carries one of the three tags.

    Attributes:
        OK: The file is in the current format and can be opened as it is.
        OLD_FORMAT: The file is in an older format. Opening it upgrades it and
            leaves a backup of the original beside it; every action stays
            available.
        NEWER_FORMAT: The file was written by a newer version of the
            application. Nothing here can read it, and nothing here should try
            to.
        UNREADABLE: The file is not a project this code can make sense of. The
            picker shows the cause instead of the actions.
    """

    OK = "ok"
    OLD_FORMAT = "old_format"
    NEWER_FORMAT = "newer_format"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class ProjectFileInfo:
    """
    One row of the register.

    Attributes:
        path: Full path to the file.
        file_name: The file's name within the data directory, which is how
            every other function here addresses it.
        name: The project name stored in the file. Empty when the file does not
            carry a usable one, in which case a screen shows file_name instead.
        item_count: How many items the file holds. Zero when it could not be
            read.
        vote_count: How many votes the file holds. Zero when it could not be
            read.
        modified: When the project was last edited: the ``modified`` timestamp
            stored inside the file, falling back to the file's own modification
            time when there is no usable stored one, and None when even that
            cannot be read.

            The stored timestamp is what "Modified" means to someone reading
            the register. The file's own time is not: opening an old-format
            project migrates it, which rewrites the file and bumps its mtime,
            so a register reporting mtime would show every migrated project as
            edited at the moment its owner merely looked at it. The migration
            re-save deliberately preserves the stored timestamp for exactly
            this reason.

            The fallback exists because an unreadable file has no stored
            timestamp to report, and because a readable file whose ``modified``
            is missing or is not a date is one of the deep faults the probe
            does not chase - reporting the file's time beats reporting nothing.
        condition: Which of the four states the file is in.
        reason: Why the condition is not OK, phrased for a person. Empty when
            the condition is OK.
    """

    path: Path
    file_name: str
    name: str
    item_count: int
    vote_count: int
    modified: Optional[datetime]
    condition: ProjectCondition
    reason: str = ""

    @property
    def openable(self) -> bool:
        """
        Check whether this application can open the file at all.

        This is a fact about the file rather than a policy about the screen:
        an unreadable file has nothing to open and a newer-format file makes
        :func:`~src.data.format_version.upgrade` raise. Whether the picker
        greys the row's actions out or hides them is still the screen's call.

        Returns:
            bool: True for a current or an older-format file.
        """
        return self.condition in (ProjectCondition.OK, ProjectCondition.OLD_FORMAT)

    @property
    def display_name(self) -> str:
        """
        Return the name to put in the register's Project column.

        Returns:
            str: The stored project name, falling back to the file name when
            the file carries no usable one.
        """
        return self.name or self.file_name


def _modified_time(path: Path) -> Optional[datetime]:
    """
    Read a file's modification time.

    Args:
        path: The file to stat.

    Returns:
        Optional[datetime]: The modification time, or None when the file cannot
        be stat'ed - it may have been deleted between the listing and the
        probe.
    """
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def _stored_modified(
    data: dict, fallback: Optional[datetime]
) -> Optional[datetime]:
    """
    Read the project's own modified timestamp out of the file.

    Parsed the way :meth:`~src.models.project.Project.from_dict` parses it, so
    the register and an opened project agree on when the project was last
    edited.

    Args:
        data: The parsed project dictionary.
        fallback: What to report when the file carries no usable timestamp,
            normally the file's own modification time.

    Returns:
        Optional[datetime]: The stored timestamp, or the fallback. A missing or
        unparseable value is not an error here: the probe checks the top-level
        shape and leaves the deep faults to whatever opens the file.
    """
    raw = data.get("modified")
    if not isinstance(raw, str):
        return fallback

    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return fallback


def _entry_count(value) -> int:
    """
    Count the entries of an "items" or "votes" value.

    Args:
        value: The value read out of the project dictionary.

    Returns:
        int: How many entries it holds, or 0 when it holds none or is not a
        list. A value of the wrong shape is reported as unreadable elsewhere;
        this only has to avoid raising.
    """
    return len(value) if isinstance(value, list) else 0


def _valid_entry_list(value) -> bool:
    """
    Check an "items" or "votes" value the way from_dict checks it.

    Args:
        value: The value read out of the project dictionary.

    Returns:
        bool: True when :meth:`~src.models.project.Project.from_dict` would
        accept it. A missing key is accepted, because from_dict reads it as an
        empty list.
    """
    if value is None:
        return True
    return isinstance(value, list) and all(isinstance(entry, dict) for entry in value)


def _top_level_shape_error(data: dict) -> Optional[str]:
    """
    Find the first top-level key of a project file that is the wrong shape.

    These are the checks :meth:`~src.models.project.Project.from_dict` makes on
    the top level of the file, in the same order, and no more. Anything nested
    is deliberately left alone: a probe that checked an item entry's keys or
    parsed a timestamp would be constructing the project it exists not to
    construct. So passing this is not a promise that the file opens, only that
    it is shaped like a project.

    Args:
        data: The parsed project dictionary, already known to be a dict.

    Returns:
        Optional[str]: Why the file is not shaped like a project, phrased for a
        person, or None when the top level is right.
    """
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return "The file carries no project name"

    for key in ("items", "votes"):
        if not _valid_entry_list(data.get(key)):
            return f"The file's '{key}' is not a list of objects"

    settings = data.get("settings")
    if settings is not None and not isinstance(settings, dict):
        return "The file's 'settings' is not an object"

    slots = data.get("slots")
    if slots is not None and (
        not isinstance(slots, list)
        or not all(isinstance(slot, str) for slot in slots)
    ):
        return "The file's 'slots' is not a list of names"

    labels = data.get("slot_labels")
    if labels is not None and (
        not isinstance(labels, dict)
        or not all(
            isinstance(slot, str) and isinstance(label, str)
            for slot, label in labels.items()
        )
    ):
        return "The file's 'slot_labels' is not an object of short labels"

    return None


def _unreadable(
    path: Path, modified: Optional[datetime], reason: str
) -> ProjectFileInfo:
    """
    Build the register row of a file that cannot be read.

    Args:
        path: The file.
        modified: The file's modification time, if it has one.
        reason: Why it cannot be read, phrased for a person.

    Returns:
        ProjectFileInfo: A row carrying the cause and no counts.
    """
    return ProjectFileInfo(
        path=path,
        file_name=path.name,
        name="",
        item_count=0,
        vote_count=0,
        modified=modified,
        condition=ProjectCondition.UNREADABLE,
        reason=reason,
    )


def probe_project_file(path: Path) -> ProjectFileInfo:
    """
    Read one project file's register row without modifying it.

    This is the non-mutating counterpart of
    :meth:`~src.data.project_storage.ProjectStorage.load`: it parses the JSON
    and reads the name, the two counts, the stored timestamp and the format
    version straight out of the dictionary. No
    :class:`~src.models.project.Project` is constructed, no upgrade is applied
    and nothing is written, so probing a directory full of old files leaves
    every one of them byte-identical.

    The top-level shape is checked, the nested shapes are not, so an OK row
    means the file is shaped like a project rather than that it is certain to
    open. See the module docstring for where that line is drawn.

    Args:
        path: The .pairrank file to probe.

    Returns:
        ProjectFileInfo: The row, whatever condition the file is in. Never
        raises: an unreadable file is a row with a cause on it, because the
        register has to draw a row for every file it finds.
    """
    file_modified = _modified_time(path)

    try:
        raw = path.read_bytes()
    except OSError as e:
        return _unreadable(
            path, file_modified, f"The file could not be read: {e}"
        )

    return _info_from_bytes(path, file_modified, raw)


def _info_from_bytes(
    path: Path, file_modified: Optional[datetime], raw: bytes
) -> ProjectFileInfo:
    """
    Work out a register row from a project file's bytes.

    Split out of :func:`probe_project_file` so that :func:`import_file` can
    judge an uploaded file before it has anywhere to put it.

    Args:
        path: The path the bytes belong to, or will belong to.
        file_modified: The file's own modification time, reported when the file
            carries no usable timestamp of its own.
        raw: The file's contents.

    Returns:
        ProjectFileInfo: The row. Never raises.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return _unreadable(
            path, file_modified, f"The file is not valid JSON: {e}"
        )

    if not isinstance(data, dict):
        return _unreadable(
            path,
            file_modified,
            f"The file holds {type(data).__name__} rather than a project object",
        )

    try:
        version = detect_version(data)
    except ValueError as e:
        return _unreadable(path, file_modified, str(e))

    raw_name = data.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    items = data.get("items")
    votes = data.get("votes")
    modified = _stored_modified(data, file_modified)

    if version > CURRENT_FORMAT_VERSION:
        # The shape is not checked: a newer format may well have moved the
        # keys, and guessing at what it means is how a register starts lying.
        # The counts are best-effort for the same reason.
        return ProjectFileInfo(
            path=path,
            file_name=path.name,
            name=name,
            item_count=_entry_count(items),
            vote_count=_entry_count(votes),
            modified=modified,
            condition=ProjectCondition.NEWER_FORMAT,
            reason=(
                f"The file is in format version {version}, and this "
                f"application understands version {CURRENT_FORMAT_VERSION}."
            ),
        )

    shape_error = _top_level_shape_error(data)
    if shape_error is not None:
        return _unreadable(path, file_modified, shape_error)

    old = version < CURRENT_FORMAT_VERSION
    return ProjectFileInfo(
        path=path,
        file_name=path.name,
        name=name,
        item_count=_entry_count(items),
        vote_count=_entry_count(votes),
        modified=modified,
        condition=(
            ProjectCondition.OLD_FORMAT if old else ProjectCondition.OK
        ),
        reason=(
            f"The file is in format version {version}. Opening it upgrades "
            f"it to version {CURRENT_FORMAT_VERSION} and keeps a backup of "
            "the original beside it."
            if old
            else ""
        ),
    )


def scan_directory(data_dir: Path) -> list[ProjectFileInfo]:
    """
    List every project file in a directory, without modifying any of them.

    Args:
        data_dir: The directory holding the projects.

    Returns:
        list[ProjectFileInfo]: One row per .pairrank file, ordered by file name
        so that the register's numbering is stable between visits. Empty when
        the directory holds no projects, does not exist or cannot be listed -
        an empty register is the picker's empty state, not an error.
    """
    try:
        if not data_dir.is_dir():
            return []
        # The glob is case-insensitive on Windows and on the SMB shares this
        # application is usually pointed at, so it also finds TASTING.PAIRRANK;
        # the suffix is then checked exactly, because everything downstream
        # checks it exactly. :meth:`~src.data.project_storage.ProjectStorage.load`
        # refuses a differently-cased extension and so does
        # :func:`resolve_project_path`, so a row for such a file would be one
        # the register could draw and nothing could open - listed and
        # unreachable, by the desktop app as much as by the web one.
        paths = [
            path
            for path in data_dir.glob(f"*{ProjectStorage.FILE_EXTENSION}")
            if path.suffix == ProjectStorage.FILE_EXTENSION
        ]
    except OSError:
        return []

    # Case-insensitive first so the order reads naturally, then case-sensitive
    # to break the ties that leaves on a case-sensitive filesystem.
    paths.sort(key=lambda path: (path.name.casefold(), path.name))
    return [probe_project_file(path) for path in paths]


def _file_stem(name: str) -> str:
    """
    Turn a project name into the stem of a file name.

    Args:
        name: The project name, or a file name to base the stem on.

    Returns:
        str: A safe, non-empty, length-capped stem.
    """
    stem = safe_project_filename(name or "").strip()[:MAX_FILE_STEM_LENGTH].strip()
    return stem or DEFAULT_FILE_STEM


def unique_file_name(data_dir: Path, name: str) -> str:
    """
    Choose a file name for a project that nothing in the directory holds yet.

    ``safe_project_filename`` has neither an empty guard nor a length cap -
    an empty name goes in and an empty name comes out - and its behaviour is
    pinned by tests, so both gaps are closed here instead: a name that
    sanitizes away becomes DEFAULT_FILE_STEM and a long one is truncated.

    Collisions are resolved with a " (2)", " (3)" suffix, compared
    case-insensitively because the application's own filesystem is, and two
    names differing only in case would collide there whatever this returned.

    Args:
        data_dir: The directory the file will live in.
        name: The project name, or a file name to base it on.

    Returns:
        str: A file name, extension included, that no file in the directory
        currently uses.
    """
    stem = _file_stem(name)

    try:
        taken = {
            path.name.casefold()
            for path in data_dir.glob(f"*{ProjectStorage.FILE_EXTENSION}")
        }
    except OSError:
        taken = set()

    candidate = ensure_pairrank_suffix(Path(stem)).name
    if candidate.casefold() not in taken:
        return candidate

    for n in count(2):
        suffixed = f"{stem}{_COLLISION_SUFFIX.format(n=n)}"
        candidate = ensure_pairrank_suffix(Path(suffixed)).name
        if candidate.casefold() not in taken:
            return candidate


def resolve_project_path(data_dir: Path, file_name: str) -> Path:
    """
    Turn a project's file name into the path it is allowed to name.

    **This is the traversal boundary.** The web addresses projects by file name
    alone, so a name arriving from a browser must not be able to reach a path
    of its own choosing. Everything that takes a file name from outside - a
    route opening one project, renaming one, deleting one - goes through here
    rather than joining the name onto the directory itself. It is public for
    that reason: the check is easy to forget and expensive to get wrong, and
    three routes each writing their own version is how one of them ends up
    subtly different.

    :func:`probe_project_file` and :func:`scan_directory` deliberately take
    paths instead, because they are handed paths the register itself produced.

    Args:
        data_dir: The directory projects live in.
        file_name: The name as given, with no directory part.

    Returns:
        Path: ``data_dir`` joined with the name. The file need not exist.

    Raises:
        ValueError: If the name is empty, holds a path separator or a drive
            marker, refers to a directory rather than a file in it, or does not
            name a .pairrank file.
    """
    return data_dir / _checked_file_name(file_name)


def _checked_file_name(file_name: str) -> str:
    """
    Check that a file name addresses a file in the data directory and no other.

    Args:
        file_name: The name as given.

    Returns:
        str: The name, stripped.

    Raises:
        ValueError: If the name is empty, holds a path separator or a drive
            marker, refers to a directory rather than a file in it, or does not
            name a .pairrank file.
    """
    name = (file_name or "").strip()
    if not name:
        raise ValueError("A project file name is required")

    # Both separators and the drive marker are checked whatever platform this
    # runs on, because pathlib only recognizes the ones native to it and the
    # name may have been typed on the other kind of machine.
    if "/" in name or "\\" in name or ":" in name:
        raise ValueError(
            f"A project file name cannot hold a path separator: {file_name!r}"
        )
    if name in (".", "..") or Path(name).name != name:
        raise ValueError(
            f"A project file name cannot refer to another directory: {file_name!r}"
        )
    # Case-sensitive, and :func:`scan_directory` filters its glob the same way
    # so that listing and addressing agree about what a project file is. See
    # the note there: the decision is made by
    # :meth:`~src.data.project_storage.ProjectStorage.load`, which refuses a
    # differently-cased extension outright.
    if Path(name).suffix != ProjectStorage.FILE_EXTENSION:
        raise ValueError(
            f"A project file must have the {ProjectStorage.FILE_EXTENSION} "
            f"extension: {file_name!r}"
        )
    return name


def import_file(data_dir: Path, file_name: str, raw_bytes: bytes) -> ProjectFileInfo:
    """
    Take an uploaded project file into the data directory.

    The bytes are written exactly as they arrived, so an old-format file stays
    an old-format file and is upgraded the first time it is actually opened,
    with the backup that goes with that. An import is not an opening.

    A file whose name is already taken is given a suffixed one rather than
    overwriting: an import should never be able to destroy a project that is
    already in the register.

    Args:
        data_dir: The directory to import into. Created if it does not exist.
        file_name: The name the file arrived under.
        raw_bytes: The file's contents.

    Returns:
        ProjectFileInfo: The row of the newly written file.

    Raises:
        ValueError: If the name does not address a .pairrank file in this
            directory, or if the contents are not a project this code can read.
            A file in a newer format is accepted, because it is a real project
            that a newer application can open; it simply arrives tagged.
        OSError: If the file cannot be written.
    """
    target = resolve_project_path(data_dir, file_name)

    verdict = _info_from_bytes(target, None, raw_bytes)
    if verdict.condition is ProjectCondition.UNREADABLE:
        raise ValueError(f"Not a readable project file: {verdict.reason}")

    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / unique_file_name(data_dir, target.stem)
    path.write_bytes(raw_bytes)

    return probe_project_file(path)


def duplicate_project_file(
    data_dir: Path, file_name: str, new_name: str
) -> ProjectFileInfo:
    """
    Copy a project in the register, keeping its items and dropping its votes.

    This is the register's copy, taking a file it has listed by name and
    putting the result back in the same directory;
    :meth:`~src.app.session.ProjectSession.duplicate_without_votes` is the open
    project's copy, taking a live project and a destination the user has
    chosen. They share
    :meth:`~src.data.project_storage.ProjectStorage.create_copy` and differ in
    everything around it, so neither is the other one in disguise. They are
    named apart because two different signatures behind one name in one
    namespace is how a caller ends up reading the wrong docstring.

    The source is *loaded*, not probed, because the copy has to be written in
    the current format. That means an old-format source is migrated here, with
    its backup, exactly as opening it would have done - which is honest, since
    duplicating is something the user asked for.

    Args:
        data_dir: The directory holding the source, and where the copy goes.
        file_name: Name of the file to copy, within that directory.
        new_name: Name for the copy.

    Returns:
        ProjectFileInfo: The row of the newly written copy.

    Raises:
        FileNotFoundError: If the source file does not exist.
        ValueError: If the name does not address a .pairrank file in this
            directory, if the source cannot be read, or if new_name is empty.
        OSError: If the copy cannot be written.
    """
    source_path = resolve_project_path(data_dir, file_name)
    if not (new_name or "").strip():
        raise ValueError("A name for the copy is required")

    source: Project = ProjectStorage.load(source_path)
    target = data_dir / unique_file_name(data_dir, new_name)

    ProjectStorage.create_copy(source, new_name, target)
    return probe_project_file(target)
