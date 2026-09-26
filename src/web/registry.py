"""The open-project cache: one live project per file, with a lock each.

The desktop app holds one project open at a time and owns it for as long as the
window is up. A server has neither of those luxuries: several requests arrive
for several projects, in any order, and each has to find the project already
loaded rather than re-reading the file. So the registry keeps one
:class:`~src.app.session.ProjectSession` per file, keyed by the file's resolved
path, and hands the same one to every request that asks for it.

Two things make that safe.

**A lock per path.** Every mutation runs inside the lock for the file it
touches, so two requests cannot interleave a vote and a retire over the same
in-memory project or race each other to write the file. Locks are per path
rather than global because a request about one project has no business waiting
on a request about another. A lock lives for as long as anyone holds it, waits
for it or has the project open, and is discarded afterwards: see
:meth:`ProjectRegistry.locked`, which is the only way to take one.

**An mtime check before every mutation.** The whole point of ``.pairrank``
files is that the desktop app and the web app share them, which means the file
under a loaded project can change while the server is holding it - typically
the desktop app saving over SMB. Mutating the stale copy and saving it would
silently throw the other edit away, so the registry compares the file's stamp
to the one it loaded, reloads when they differ, and leaves a notice for the
screen to tell the user their view was replaced. Exactly one screen takes that
notice, and taking it is the only way to read it. The check is on the mutation
path only: a read that shows a slightly stale ranking is harmless, while a
write over a changed file is not, and re-stat'ing on every read would make the
notice appear on pages that have nothing to say about it.

Projects are addressed by **file name**, never path. The check for that is
:func:`~src.app.register.resolve_project_path`, which the register already owns
and this module reuses rather than re-deriving.
"""

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from src.app.register import resolve_project_path
from src.app.session import ProjectSession
from src.data.errors import ProjectFormatError
from src.data.project_storage import ProjectStorage
from src.models.project import Project


logger = logging.getLogger(__name__)


class ProjectNotFoundError(LookupError):
    """
    No project of that name is available under the data directory.

    Raised both for a name that does not address a file in the data directory
    at all - a traversal attempt, a name with a separator in it, a name without
    the ``.pairrank`` extension - and for a well-formed name with no file
    behind it. The two are one error on purpose: a browser asking about a file
    it has no business naming gets the same answer as one asking about a file
    that is not there, which is 404 either way and tells an attacker nothing.
    """


class ProjectUnreadableError(ValueError):
    """
    A project file is present but cannot be turned into a project.

    This covers the damage the typed format errors do not: JSON that does not
    parse, an entry missing a key it needs, a timestamp that is not a date.
    :class:`~src.data.errors.ProjectFormatError` and its subclasses are left
    alone and pass through, because "written by a newer application" is a
    different page from "damaged" and only the raiser can tell them apart.
    """


@dataclass(frozen=True)
class LastChange:
    """
    The last change this server made to one project, as a screen describes it.

    Held in memory on the project's entry, never in the file or a cookie: it is
    the one thing a sentence like "Deleted (10) Oil King and its 2 votes · 21:06"
    needs that the project cannot supply afterwards - what went, and when. A
    restart, or the entry being forgotten, loses it, and the screen falls back
    to the project's stored modified time.

    Attributes:
        kind: Which change, in the screen's own words for it (Items' ``done``).
        item_id: The item it was about; for a deletion, the one that went.
        label: How the sentence names its subject, fixed at the time.
        votes: The votes that went with it; 0 unless something was deleted.
        time: When the change was made.
    """

    kind: str
    item_id: str
    label: str
    votes: int
    time: datetime


def _stamp(path: Path) -> Optional[tuple[int, int]]:
    """
    Take the fingerprint used to notice that a file changed underneath us.

    Size rides along with the modification time because a filesystem's mtime
    resolution is coarser than a quick edit: a network share can hand back the
    same timestamp for two writes a moment apart, and a different length is
    then the only evidence left.

    Args:
        path: The project file.

    Returns:
        Optional[tuple[int, int]]: The file's modification time in nanoseconds
        and its size, or None when it cannot be stat'ed - which is itself a
        change worth reloading over.
    """
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def load_project(path: Path) -> Project:
    """
    Read a project file, turning every failure into one a screen can render.

    Args:
        path: The project file to load.

    Returns:
        Project: The loaded project, upgraded in place if it was in an older
        format, exactly as opening it from the desktop app would do.

    Raises:
        ProjectNotFoundError: If the file does not exist.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file cannot be read or parsed.
    """
    try:
        return ProjectStorage.load(path)
    except FileNotFoundError as e:
        raise ProjectNotFoundError(f"No project file at {path.name}") from e
    except ProjectFormatError:
        # Already says which kind of unusable this file is, which is the whole
        # reason the typed errors exist.
        raise
    except (OSError, ValueError) as e:
        # Every deep fault arrives as a ValueError, including the ones the
        # register's shallow probe cannot see - an item entry missing a key, a
        # `created` that is not a date - because ProjectStorage.load wraps
        # them. That is what lets the picker tag a file OK and still answer
        # honestly when opening it fails: see `open_project` in
        # src/web/routes/projects.py.
        raise ProjectUnreadableError(f"{path.name} could not be read: {e}") from e


class OpenProject:
    """
    One project held open by the registry.

    Attributes:
        path: The resolved path of the file, which is also the registry key.
        session: The session over the loaded project. Replaced wholesale when
            the file changes on disk, so hold the OpenProject rather than the
            session if you intend to keep a reference.
        reloaded_from_disk: Whether a reload has happened that nothing has
            reported to the user yet. See :meth:`take_reload_notice`.
        last_change: The last change made through this entry, or None. Set
            only by :meth:`Mutation.record_change`, so only under the file's
            lock; a :class:`LastChange` is immutable and is replaced whole, so
            reading it needs no lock. It survives a reload from disk: what this
            server did, and when, is still true of the file.
    """

    def __init__(self, path: Path):
        """
        Load a project and open a session over it.

        Args:
            path: The resolved path of the project file.

        Raises:
            ProjectNotFoundError: If the file does not exist.
            ProjectFormatError: If the file's format version is unusable.
            ProjectUnreadableError: If the file cannot be read or parsed.
        """
        self.path = path
        self.reloaded_from_disk = False
        self.last_change: Optional[LastChange] = None
        self._stamp: Optional[tuple[int, int]] = None
        self.session = self._open_session(path)

    def _open_session(self, path: Path) -> ProjectSession:
        """
        Build a session that keeps this entry's stamp honest.

        The stamp is taken **after** the load, for two reasons. Loading an
        old-format file migrates it, which rewrites the file; a stamp taken
        beforehand would describe a file that no longer exists and make the
        very next mutation reload for nothing. And every session mutation
        saves, which moves the mtime again - hence the save callback, without
        which the registry would mistake its own write for somebody else's edit.

        Args:
            path: The project file to load.

        Returns:
            ProjectSession: A session over the freshly loaded project.
        """
        project = load_project(path)
        session = ProjectSession(project, on_saved=lambda _project: self._restamp())
        self._restamp()
        return session

    def _restamp(self) -> None:
        """Record the file's fingerprint as it is now."""
        self._stamp = _stamp(self.path)

    def changed_on_disk(self) -> bool:
        """
        Check whether the file differs from what this entry was loaded from.

        Returns:
            bool: True when something outside this process has written the
            file since it was loaded or last saved.
        """
        return _stamp(self.path) != self._stamp

    def reload_if_changed(self) -> None:
        """
        Re-read the file if it has changed underneath this entry.

        Deliberately answers with nothing. The reload is recorded as a pending
        notice and :meth:`take_reload_notice` is the one way to learn about it,
        because a caller that both read a returned flag and left the pending
        one standing would report one event twice: once on the page it renders
        and again on the next page anybody opens.

        Args:
            None.

        Raises:
            ProjectNotFoundError: If the file has since been deleted.
            ProjectFormatError: If it has been replaced by one in an unusable
                format version.
            ProjectUnreadableError: If it has been replaced by one that cannot
                be read.
        """
        if not self.changed_on_disk():
            return

        logger.info("Reloading %s: the file changed on disk", self.path.name)
        self.session = self._open_session(self.path)
        self.reloaded_from_disk = True

    def take_reload_notice(self) -> bool:
        """
        Read and clear the pending "changed on disk" notice.

        A mutation that answers with a redirect cannot render the notice
        itself, so the fact is held until a request renders a page and takes
        it. A mutation that renders its own page takes it there and then,
        through :meth:`Mutation.take_reload_notice`. Either way taking it
        clears it: the notice describes one event and should be reported once,
        rather than following the user around the application.

        Returns:
            bool: True when there was an unreported reload.
        """
        pending = self.reloaded_from_disk
        self.reloaded_from_disk = False
        return pending


@dataclass(frozen=True)
class Mutation:
    """
    The handle :meth:`ProjectRegistry.mutate` lends for the length of an edit.

    There is no ``reloaded`` flag to read. Whether the file had changed on disk
    before the edit began is asked for with :meth:`take_reload_notice`, and
    asking consumes it: a route that could see the fact without consuming it
    would render the notice on its own page and leave it pending for the next
    page as well, which is the same event reported twice.

    Attributes:
        session: The session to edit. Valid only inside the ``with`` block
            that produced it; outside it, nothing holds the file's lock.
        entry: The open project being edited, for the routes that need the
            entry itself rather than the session.
    """

    session: ProjectSession
    entry: OpenProject

    def take_reload_notice(self) -> bool:
        """
        Read and clear the "changed on disk" notice, for a page rendered here.

        A route that renders its own answer calls this and draws the notice; a
        route that redirects does not, and the request that follows finds the
        notice still pending and draws it there.

        Returns:
            bool: True when the file had changed on disk and was re-read before
            this edit began, meaning the user has just acted on a project that
            is not quite the one the page was drawn from.
        """
        return self.entry.take_reload_notice()

    def record_change(self, kind: str, item_id: str, label: str, votes: int = 0) -> LastChange:
        """
        Remember this edit as the project's last change, timed now.

        Called inside the ``with`` block, so under the file's lock, after the
        session has saved: a refused or abandoned edit records nothing.

        Args:
            kind: Which change.
            item_id: The item it was about.
            label: How a sentence names its subject.
            votes: The votes that went with it.

        Returns:
            LastChange: The record, which replaces the previous one.
        """
        change = LastChange(kind, item_id, label, votes, datetime.now())
        self.entry.last_change = change
        return change


class ProjectRegistry:
    """
    The open projects of one data directory.

    One instance per application, built by the factory and reached through
    :func:`~src.web.deps.get_registry`.
    """

    def __init__(self, data_dir: Path):
        """
        Initialize an empty registry.

        Args:
            data_dir: The directory holding the projects. Need not exist yet;
                an empty directory is the picker's empty state, not an error.
        """
        self.data_dir = data_dir
        self._entries: dict[Path, OpenProject] = {}
        self._locks: dict[Path, threading.RLock] = {}
        # How many callers are inside or waiting for each lock. This is what
        # lets a lock be dropped again: a lock nobody holds, nobody is queued
        # for and no open project needs is guarding nothing, and keeping it
        # would let a stream of names for files that are not there grow this
        # dictionary without bound.
        self._lock_users: dict[Path, int] = {}
        # Guards the three dictionaries above, and nothing else. It is never
        # held while a file is read or written, so a slow project cannot block
        # a request about a different one.
        self._guard = threading.Lock()

    def resolve(self, project_id: str) -> Path:
        """
        Turn a project id into the one path it is allowed to name.

        A project id is a **file name** under the data directory. Anything else
        - a parent reference, either separator, a drive marker, a name without
        the ``.pairrank`` extension - is not a project this application has.

        Args:
            project_id: The file name as it arrived from the browser.

        Returns:
            Path: The resolved path, which is also this project's registry key.
            The file need not exist.

        Raises:
            ProjectNotFoundError: If the id does not address a project file in
                the data directory.
        """
        try:
            path = resolve_project_path(self.data_dir, project_id)
        except ValueError as e:
            logger.warning("Refused project id %r: %s", project_id, e)
            raise ProjectNotFoundError(str(e)) from e
        return path.resolve()

    @contextmanager
    def locked(self, path: Path) -> Iterator[None]:
        """
        Hold the lock guarding one project file for the length of a block.

        Public because the routes that create, import, duplicate and delete
        files need the same lock as the ones that edit them, and a second lock
        over the same file would guard nothing. It is the *only* way to take
        that lock: handing the bare lock out instead would leave the registry
        unable to tell whether anybody still wanted it, and therefore unable to
        drop it.

        One path has exactly one lock for as long as anyone is inside it,
        queued for it, or has the project open - which is the whole guarantee.
        Outside those cases the lock is discarded, because a lock nobody can
        reach through this method is a lock no second caller can collide with,
        and a file need not exist to be locked: creating and importing take the
        lock over a path before there is anything there.

        Args:
            path: A resolved project path.

        Yields:
            None: The lock is held for the body of the block. It is reentrant,
            so an operation inside it may call another that takes it too.
        """
        with self._guard:
            lock = self._locks.get(path)
            if lock is None:
                lock = threading.RLock()
                self._locks[path] = lock
            self._lock_users[path] = self._lock_users.get(path, 0) + 1

        try:
            with lock:
                yield
        finally:
            with self._guard:
                remaining = self._lock_users[path] - 1
                if remaining:
                    self._lock_users[path] = remaining
                else:
                    del self._lock_users[path]
                    # Only now is it certain that no other caller holds this
                    # object, so replacing it later cannot split one path's
                    # traffic across two locks.
                    if path not in self._entries:
                        del self._locks[path]

    def open(self, project_id: str) -> OpenProject:
        """
        Return the open project for an id, loading it the first time.

        Args:
            project_id: The project's file name.

        Returns:
            OpenProject: The cached entry. The same id yields the same object
            for as long as it stays open, so two requests about one project
            share one in-memory project rather than two copies of it.

        Raises:
            ProjectNotFoundError: If the id is not a project file in the data
                directory, or names no existing file.
            NewerFormatError: If the file was written by a newer application.
            ProjectFormatError: If the file's format version cannot be reached.
            ProjectUnreadableError: If the file cannot be read or parsed.
        """
        path = self.resolve(project_id)
        # Under the file's own lock, so that two requests for a project nobody
        # has opened yet do not both read and both construct it. When the load
        # fails - which for a name a browser invented is the usual outcome -
        # the block leaves no entry behind, and the lock goes with it.
        with self.locked(path):
            entry = self._entries.get(path)
            if entry is None:
                entry = OpenProject(path)
                with self._guard:
                    self._entries[path] = entry
                logger.info("Opened %s", path.name)
            return entry

    def session(self, project_id: str) -> ProjectSession:
        """
        Return the session for an id, for reading.

        Mutations go through :meth:`mutate` instead: this takes no lock and
        makes no mtime check, so editing through it would race another request
        and could write over an edit made outside this process.

        Args:
            project_id: The project's file name.

        Returns:
            ProjectSession: The open session.

        Raises:
            ProjectNotFoundError: If the id names no project in the directory.
            ProjectFormatError: If the file's format version is unusable.
            ProjectUnreadableError: If the file cannot be read or parsed.
        """
        return self.open(project_id).session

    @contextmanager
    def mutate(self, project_id: str) -> Iterator[Mutation]:
        """
        Hold a project's lock for the length of one edit.

        The sequence the plan asks for, in one place so no route has to
        remember it: take the lock, compare the file's stamp against what was
        loaded, reload and flag a notice if it moved, then let the caller
        mutate. The save is the session's own, and is atomic.

        Args:
            project_id: The project's file name.

        Yields:
            Mutation: The session to edit, and the notice-taking a route that
            renders its own page needs.

        Raises:
            ProjectNotFoundError: If the id names no project in the directory.
            ProjectFormatError: If the file's format version is unusable.
            ProjectUnreadableError: If the file cannot be read or parsed.
        """
        path = self.resolve(project_id)
        with self.locked(path):
            entry = self.open(project_id)
            entry.reload_if_changed()
            # The session is read off the entry after the reload, because a
            # reload replaces it wholesale.
            yield Mutation(session=entry.session, entry=entry)

    def forget(self, project_id: str) -> None:
        """
        Drop a project from the cache, so the next open re-reads the file.

        The lock outlives the entry for as long as anyone is inside it or
        waiting on it - a file that is deleted and later recreated under the
        same name stays guarded by the same lock throughout the operations that
        are in flight over it - and is discarded once nobody is.

        Args:
            project_id: The project's file name.

        Raises:
            ProjectNotFoundError: If the id does not address a project file in
                the data directory.
        """
        path = self.resolve(project_id)
        with self.locked(path):
            with self._guard:
                self._entries.pop(path, None)
