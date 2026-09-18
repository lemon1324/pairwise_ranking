"""The drawing register: the sheet the application opens on.

One row per ``.pairrank`` file in the data directory, with the condition each
file is in, and the five things that can be done from here: open one, start
one, copy one without its votes, download one, and take one in from the desktop
app. There is no file dialog on the web, so this listing *is* the file dialog.

Three shapes of route, and they are worth telling apart before reading any of
them.

**The page** (:func:`register`) draws the whole sheet. Its query describes the
state completely - which form is open, what was typed into it, which row is
selected, why the last one was refused - so every state of this screen has an
address. That is what the review captures are taken against, and it is why a
refused form is answered with a redirect into that query rather than with a
state only a form post can reach.

**The callout fragments** answer with the popover for one row and nothing
around it. The folding engine (``static/js/sheet.js``) fires ``sheet:select``
on the row it has selected, htmx hears it there and puts the fragment in
``#row-callout``, which ``base.html`` keeps outside every region that is ever
swapped. New and Import have no row of their own, so the page draws a ghost row
for them and selecting it is what opens their form - the engine has to have
something to hang a callout on.

**The mutations** create, duplicate and import files. Each takes the registry's
lock over the file it is about to write, which is the lock the screens take to
edit a project, so a create and an edit cannot interleave over one path. Each
is an ordinary form post answered with a 303, and none of them needs htmx: the
forms work with the engine and without it, and a reload cannot repeat a write.

Opening is the one action that can fail on a file the register called OK. The
register's probe checks the top level of a file and stops there - see
:mod:`src.app.register` - so a project whose *item entries* are malformed is
listed as openable and is not. :func:`open_project` therefore really opens the
project rather than trusting the tag, and lets the failure reach the
damaged-file page.
"""

import logging
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.app.register import (
    ProjectCondition,
    ProjectFileInfo,
    default_file_name,
    duplicate_project_file,
    import_file,
    probe_project_bytes,
    probe_project_file,
    resolve_project_path,
    scan_directory,
    unique_file_name,
)
from src.data.errors import ProjectFormatError
from src.data.project_storage import ProjectStorage

from ..config import WebConfig
from ..deps import Principal, get_config, get_current_user, get_registry
from ..registry import (
    ProjectNotFoundError,
    ProjectRegistry,
    ProjectUnreadableError,
)
from ..urls import DEFAULT_SHEET, PROJECTS_PREFIX, project_url, register_url


logger = logging.getLogger(__name__)

router = APIRouter()

# The row the New and Import forms hang their callout on. It is not a file
# name - every real row is one, and no file name can be this - so it can never
# collide with a project.
GHOST_ROW_ID = "__form"

# The forms the register can have open. Anything else in the query is no form
# at all: a mistyped address should draw the register, not an error page.
FORM_NEW = "new"
FORM_IMPORT = "import"
FORM_DUPLICATE = "duplicate"
FORMS = (FORM_NEW, FORM_IMPORT, FORM_DUPLICATE)

# The keys the register's title block lists. New (N) and Import (I) are drawn
# on their own cells and declare their shortcuts there.
REGISTER_KEYS = (
    (("↑", "↓"), "select"),
    (("↵",), "open"),
    (("D",), "duplicate"),
    (("Esc",), "deselect"),
)

# The register's columns, in the shape the parts-list macro wants them.
REGISTER_COLUMNS = (
    {"label": "No.", "width": "3rem", "class": "c-find"},
    {"label": "Project"},
    {"label": "Items", "width": "4.5rem", "class": "n c-phone-hide"},
    {"label": "Votes", "width": "4.5rem", "class": "n"},
    {"label": "Modified", "width": "10rem", "class": "c-cat"},
)

# The tag drawn after the name of a file that is not in the current format.
# Words, not colour: such a row is also set in ink 3, and ink 3 on its own is
# not a signal a reader with a colour-vision deficiency or low contrast
# sensitivity can rely on.
CONDITION_TAGS = {
    ProjectCondition.OLD_FORMAT: "Old format",
    ProjectCondition.NEWER_FORMAT: "Newer format",
    ProjectCondition.UNREADABLE: "Unreadable",
}

# What the Note cell says after a mutation, keyed by the `done` the mutation
# redirected with. The file name is filled in from the register's own scan and
# never from the query, so nothing a browser sent is echoed onto the sheet.
DONE_NOTES = {
    "created": "Created {file}.",
    "imported": "Imported {file}.",
    "duplicated": "Duplicated {file}, without votes.",
}

# What the Note cell says the rest of the time.
STANDING_NOTE = (
    "Every .pairrank file in {directory} is listed. Copy projects from the "
    "desktop app into the appdata share to see them here."
)

# How the register writes a timestamp. No seconds: this is when a project was
# last worked on, not a log line.
MODIFIED_FORMAT = "%Y-%m-%d %H:%M"

# Drawn in a count column that cannot be trusted. A newer-format file may have
# moved its keys, and an unreadable one was never counted at all.
NO_FIGURE = "–"

# The most an uploaded project may weigh. A project is JSON someone typed their
# way into; anything past this is not one, and reading it into memory to find
# that out is how a listening process gets knocked over.
MAX_IMPORT_BYTES = 32 * 1024 * 1024

# Why an import was refused. The form is a plain post, so the answer is a
# redirect and the reason travels as one of these codes rather than as the
# file's own error text through a query string.
IMPORT_ERRORS = {
    "type": (
        "That is not a project file. Import takes .pairrank files; old CSV "
        "data is migrated by the desktop app."
    ),
    "unreadable": "That .pairrank file could not be read, so nothing was imported.",
    "size": "That file is too large to be a project, so nothing was imported.",
    "empty": "Choose a .pairrank file to import.",
}


def _templates(request: Request) -> Jinja2Templates:
    """
    Reach the application's template environment.

    Args:
        request: The incoming request.

    Returns:
        Jinja2Templates: The environment the factory built.
    """
    return request.app.state.templates


def _fragment_url(request: Request, path: str, **query) -> str:
    """
    Build the address of one of this module's fragments.

    Args:
        request: The incoming request, for the reverse proxy's prefix.
        path: The path under :data:`~src.web.urls.PROJECTS_PREFIX`.
        **query: Query parameters; the empty ones are left out.

    Returns:
        str: The path, prefix and query included.
    """
    pairs = [
        f"{key}={quote(str(value), safe='')}"
        for key, value in query.items()
        if value
    ]
    suffix = f"?{'&'.join(pairs)}" if pairs else ""
    root = request.scope.get("root_path", "")
    return f"{root}{PROJECTS_PREFIX}{path}{suffix}"


def _row(request: Request, info: ProjectFileInfo, number: int, form: str) -> dict:
    """
    Turn one probed file into the row the template draws.

    Args:
        request: The incoming request, for the row's own addresses.
        info: The file as the register probed it.
        number: The row's find number, from 1.
        form: The form the page has open, so that the row being duplicated asks
            for the duplicate form rather than for the plain actions.

    Returns:
        dict: The row.
    """
    # A newer-format file may have moved its keys and an unreadable one was
    # never read, so neither has counts worth printing.
    counted = info.condition in (ProjectCondition.OK, ProjectCondition.OLD_FORMAT)
    screen = "duplicate" if form == FORM_DUPLICATE else "callout"
    return {
        "id": info.file_name,
        "number": number,
        "name": info.display_name,
        "file_name": info.file_name,
        "tag": CONDITION_TAGS.get(info.condition),
        # A file this application cannot open is drawn like a retired item:
        # ink 3, with a tag saying which kind of unusable it is.
        "dimmed": not info.openable,
        # Not "items" and "votes". A template reaching a mapping key with dot
        # syntax gets the attribute first, and every mapping has an `items`
        # method - so `row.items` renders "<built-in method items of dict>" and
        # renders it silently, because it is a perfectly good object. The
        # columns are counts anyway, so they are named for what they hold.
        "item_count": str(info.item_count) if counted else NO_FIGURE,
        "vote_count": str(info.vote_count) if counted else NO_FIGURE,
        "modified": (
            info.modified.strftime(MODIFIED_FORMAT) if info.modified else NO_FIGURE
        ),
        "callout_url": project_url(request, info.file_name, screen),
    }


def _note(rows: list, done: str, selected: str, directory: Path) -> str:
    """
    Choose what the Note cell says.

    Args:
        rows: The rows on the register.
        done: Which mutation just finished, from the query.
        selected: The file it produced, from the query.
        directory: The data directory, for the standing note.

    Returns:
        str: One sentence.
    """
    if done in DONE_NOTES:
        named = next((row for row in rows if row["id"] == selected), None)
        if named is not None:
            return DONE_NOTES[done].format(file=named["file_name"])
    return STANDING_NOTE.format(directory=directory)


def _name_taken(data_dir: Path, file_name: str) -> bool:
    """
    Check whether a file name is already in use in the data directory.

    Compared case-insensitively, because the filesystems this runs on are: two
    names differing only in case are one file on a Windows share whatever this
    answers.

    Args:
        data_dir: The directory to look in.
        file_name: The candidate name.

    Returns:
        bool: True when something of that name is already there.
    """
    try:
        return any(
            path.name.casefold() == file_name.casefold()
            for path in data_dir.glob(f"*{ProjectStorage.FILE_EXTENSION}")
        )
    except OSError:
        return False


def _draft(data_dir: Path, name: str, submitted: bool) -> tuple:
    """
    Work out what a drafted project name would be saved as, and what is wrong.

    The same check runs when the form is drawn and when it is posted, so the
    error a user reads is the one that actually stopped the write.

    Args:
        data_dir: The directory the project would be saved in.
        name: The name as typed.
        submitted: Whether this draft has been through a submit. An empty name
            is only an error once someone has pressed the button on it.

    Returns:
        tuple: The file name the project would take, empty when there is no
        name yet, and the error to draw - a mapping of ``lead`` and ``detail``
        - or None when there is nothing wrong with it.
    """
    trimmed = (name or "").strip()
    if not trimmed:
        return "", ({"lead": "Enter a name.", "detail": ""} if submitted else None)

    file_name = default_file_name(trimmed)
    if _name_taken(data_dir, file_name):
        # The path in full, as the mockup writes it: this line replaces the
        # hint that said where the project would be saved, so it has to say
        # where the file it clashes with already is.
        return file_name, {
            "lead": f"{data_dir}/{file_name} already exists.",
            "detail": "Choose another name.",
        }
    return file_name, None


def _listed(data_dir: Path, project_id: str) -> ProjectFileInfo:
    """
    Probe one file of the register, by the name a browser sent.

    Args:
        data_dir: The data directory.
        project_id: The file name.

    Returns:
        ProjectFileInfo: The row, in whatever condition the file is in.

    Raises:
        ProjectNotFoundError: If the name does not address a project file in
            the data directory, or names no file that is there. The two are one
            answer on purpose: a browser asking about a file it has no business
            naming learns nothing it did not already know.
    """
    try:
        path = resolve_project_path(data_dir, project_id)
    except ValueError as e:
        logger.warning("Refused project id %r: %s", project_id, e)
        raise ProjectNotFoundError(str(e)) from e
    if not path.is_file():
        raise ProjectNotFoundError(f"No project file at {project_id}")
    return probe_project_file(path)


@router.get("/", name="register")
async def register(
    request: Request,
    form: str = Query("", description="which form is open"),
    name: str = Query("", description="the project name being drafted"),
    project: str = Query("", description="the project the duplicate form is for"),
    selected: str = Query("", description="the row to arrive with selected"),
    submitted: int = Query(0, description="whether the draft has been posted"),
    done: str = Query("", description="which mutation just finished"),
    error: str = Query("", description="why an import was refused"),
    config: WebConfig = Depends(get_config),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Draw the register of every project in the data directory.

    Args:
        request: The incoming request.
        form: "new", "import" or "duplicate" for a form on the sheet, empty for
            the plain register. Anything else reads as empty: a mistyped
            address should draw the register rather than an error page.
        name: The draft name in the new or duplicate form.
        project: The file the duplicate form is about.
        selected: The file name of the row to arrive with selected.
        submitted: 1 when the draft has already been refused once, which is
            what makes an empty name an error rather than an empty field.
        done: Which mutation just finished, for the Note cell.
        error: Which import error to draw, for a form post that was refused.
        config: The application's configuration, for the data directory.
        user: The signed-in principal.

    Returns:
        Response: The register sheet.
    """
    form = form if form in FORMS else ""
    infos = scan_directory(config.data_dir)
    rows = [_row(request, info, i + 1, form) for i, info in enumerate(infos)]

    # The duplicate form belongs to a row, so it is only open if the row is
    # really there; the other two hang off the ghost row.
    if form == FORM_DUPLICATE and not any(row["id"] == project for row in rows):
        form = ""
    if form == FORM_DUPLICATE:
        selected = project
        rows = [
            row
            | {"callout_url": _duplicate_url(request, project, name, submitted)}
            if row["id"] == project
            else row
            for row in rows
        ]
    elif form in (FORM_NEW, FORM_IMPORT):
        selected = GHOST_ROW_ID

    ghost_url = None
    if form == FORM_NEW:
        ghost_url = _fragment_url(
            request, "/new/callout", name=name, submitted=submitted
        )
    elif form == FORM_IMPORT:
        ghost_url = _fragment_url(
            request, "/import/callout", error=error if error in IMPORT_ERRORS else ""
        )

    context = {
        "rows": rows,
        "columns": REGISTER_COLUMNS,
        "keys": REGISTER_KEYS,
        "data_dir": str(config.data_dir),
        "problem_count": sum(1 for info in infos if not info.openable),
        "note": _note(rows, done, selected, config.data_dir),
        "ghost_label": "New project" if form == FORM_NEW else "Imported file",
        "ghost_id": GHOST_ROW_ID,
        "ghost_callout_url": ghost_url,
        "selected": selected,
        # The register's own address three ways: bare, as the action of the
        # title block's two GET forms, and as the links the empty state offers.
        "register_action": register_url(request),
        "new_url": register_url(request, form=FORM_NEW),
        "import_url": register_url(request, form=FORM_IMPORT),
        "new_form": FORM_NEW,
        "import_form": FORM_IMPORT,
    }
    return _templates(request).TemplateResponse(request, "register.html", context)


def _duplicate_url(
    request: Request, project_id: str, name: str, submitted: int
) -> str:
    """
    Build the address of one project's duplicate form.

    Args:
        request: The incoming request.
        project_id: The project to copy.
        name: The draft name for the copy.
        submitted: 1 when the draft has been refused once.

    Returns:
        str: The fragment's address.
    """
    base = project_url(request, project_id, "duplicate")
    pairs = []
    if name:
        pairs.append(f"name={quote(name, safe='')}")
    if submitted:
        pairs.append("submitted=1")
    return f"{base}?{'&'.join(pairs)}" if pairs else base


@router.get(f"{PROJECTS_PREFIX}/new/callout", name="new_callout")
async def new_callout(
    request: Request,
    name: str = Query("", description="the project name being drafted"),
    submitted: int = Query(0, description="whether the draft has been posted"),
    config: WebConfig = Depends(get_config),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return the new-project form, as a fragment for the callout host.

    Args:
        request: The incoming request.
        name: The draft name to fill the field with.
        submitted: 1 when the draft has already been refused, which is what
            makes an empty field an error rather than an empty field.
        config: The application's configuration.
        user: The signed-in principal.

    Returns:
        Response: The callout.
    """
    file_name, error = _draft(config.data_dir, name, bool(submitted))
    context = {
        "title": "New project",
        "label": "Name",
        "submit_label": "Create",
        "action": _fragment_url(request, "/new"),
        "cancel_url": register_url(request),
        "name": name,
        "file_name": file_name,
        "directory": str(config.data_dir),
        "error": error,
        "detail": None,
    }
    return _templates(request).TemplateResponse(
        request, "register/callout_name_form.html", context
    )


@router.post(f"{PROJECTS_PREFIX}/new", name="create_project")
async def create_project(
    request: Request,
    name: str = Form("", description="the name for the new project"),
    config: WebConfig = Depends(get_config),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Create an empty project and come back to the register with it selected.

    Args:
        request: The incoming request.
        name: The project's name, from the form.
        config: The application's configuration.
        registry: The open-project cache, for the new file's lock.
        user: The signed-in principal.

    Returns:
        Response: A redirect to the register, or back to the form carrying the
        draft and the reason it could not be used.
    """
    trimmed = (name or "").strip()
    file_name, error = _draft(config.data_dir, trimmed, submitted=True)
    if error is not None:
        return RedirectResponse(
            register_url(request, form=FORM_NEW, name=trimmed, submitted=1),
            status_code=303,
        )

    path = registry.resolve(file_name)
    with registry.locked(path):
        config.data_dir.mkdir(parents=True, exist_ok=True)
        ProjectStorage.create_new(trimmed, path)
    logger.info("Created %s", file_name)

    return RedirectResponse(
        register_url(request, selected=file_name, done="created"), status_code=303
    )


@router.get(f"{PROJECTS_PREFIX}/import/callout", name="import_callout")
async def import_callout(
    request: Request,
    error: str = Query("", description="why an earlier import was refused"),
    config: WebConfig = Depends(get_config),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return the import form, as a fragment for the callout host.

    Args:
        request: The incoming request.
        error: The code of an error to draw in the detail area.
        config: The application's configuration.
        user: The signed-in principal.

    Returns:
        Response: The callout.
    """
    context = {
        "action": _fragment_url(request, "/import"),
        "preview_url": _fragment_url(request, "/import/preview"),
        "cancel_url": register_url(request),
        "directory": str(config.data_dir),
        "detail": (
            {"error": IMPORT_ERRORS[error]} if error in IMPORT_ERRORS else None
        ),
    }
    return _templates(request).TemplateResponse(
        request, "register/callout_import.html", context
    )


async def _read_upload(data_dir: Path, upload: Optional[UploadFile]) -> tuple:
    """
    Read an uploaded file, and say what is wrong with it if anything is.

    The *name* is judged here rather than by the importer, so that "not a
    project file" and "a project file that will not read" stay two different
    sentences.

    Args:
        data_dir: The data directory, which is what the name has to address a
            file in.
        upload: The file as it arrived, if one did.

    Returns:
        tuple: Its bytes, the name it arrived under, and a key of
        :data:`IMPORT_ERRORS` - empty when the file is worth parsing.
    """
    if upload is None or not upload.filename:
        return b"", "", "empty"

    # Browsers send a bare name, but the field is the uploader's to fill in.
    file_name = Path(upload.filename).name
    try:
        resolve_project_path(data_dir, file_name)
    except ValueError:
        return b"", file_name, "type"

    # One byte past the limit is enough to know it is over it, and is all that
    # is ever held of a file that will not be taken.
    raw = await upload.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        return b"", file_name, "size"
    return raw, file_name, ""


@router.post(f"{PROJECTS_PREFIX}/import/preview", name="preview_import")
async def preview_import(
    request: Request,
    file: Optional[UploadFile] = File(None, description="the uploaded project"),
    config: WebConfig = Depends(get_config),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Say what an uploaded file holds, before anything is written.

    Nothing is kept: the file is parsed, described and dropped, and pressing
    Import uploads it again. Holding it between the two requests would mean a
    scratch file with an owner and a lifetime, which is a great deal of
    machinery for a JSON file of a few kilobytes.

    Args:
        request: The incoming request.
        file: The file the browser has just chosen.
        config: The application's configuration.
        user: The signed-in principal.

    Returns:
        Response: The detail area of the import form, as a fragment.
    """
    raw, file_name, code = await _read_upload(config.data_dir, file)
    if code:
        detail = {"error": IMPORT_ERRORS[code]}
    else:
        detail = _describe_upload(config.data_dir, file_name, raw)

    return _templates(request).TemplateResponse(
        request,
        "register/import_detail.html",
        {
            "detail": detail,
            "directory": str(config.data_dir),
            # The drop zone still says "drop a file" until it is told
            # otherwise; the fragment carries the name out of band so the box
            # a person just used says what is now in it. Empty when nothing
            # was chosen, which leaves the invitation where it was.
            "chosen": file_name,
        },
    )


def _describe_upload(data_dir: Path, file_name: str, raw: bytes) -> dict:
    """
    Read an uploaded file's headline figures without writing it anywhere.

    Args:
        data_dir: The directory it would be saved in.
        file_name: The name it arrived under.
        raw: Its bytes.

    Returns:
        dict: Either an ``error`` sentence, or the project's name, its counts
        and the file name it would actually be saved as - which is not always
        the one it arrived with, because a name already on the register is
        suffixed rather than overwritten.
    """
    target = unique_file_name(data_dir, Path(file_name).stem)
    info = probe_project_bytes(data_dir / target, raw)
    if info.condition is ProjectCondition.UNREADABLE:
        return {"error": f"{file_name} is not a project file: {info.reason}"}
    return {
        "name": info.display_name,
        "file_name": file_name,
        # Named as in :func:`_row`, and for the same reason: `detail.items`
        # would reach the mapping's own method rather than this key.
        "item_count": info.item_count,
        "vote_count": info.vote_count,
        "target": target,
        "tag": CONDITION_TAGS.get(info.condition),
    }


@router.post(f"{PROJECTS_PREFIX}/import", name="import_project")
async def import_project(
    request: Request,
    file: Optional[UploadFile] = File(None, description="the uploaded project"),
    config: WebConfig = Depends(get_config),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Take an uploaded project file into the data directory.

    The bytes are written as they arrived, so an old-format file stays an
    old-format file and is upgraded the first time it is opened. A name that is
    already taken is suffixed rather than overwritten: an import must never be
    able to destroy a project that is already on the register.

    Args:
        request: The incoming request.
        file: The uploaded project file.
        config: The application's configuration.
        registry: The open-project cache, for the new file's lock.
        user: The signed-in principal.

    Returns:
        Response: A redirect to the register with the import selected, or back
        to the form carrying the reason it was refused.
    """
    raw, file_name, code = await _read_upload(config.data_dir, file)
    if code:
        return _refuse_import(request, file_name, code)

    # The free name is chosen before the lock because the importer chooses it
    # the same way, which makes its own search a no-op; two imports racing for
    # one name is the case this cannot cover, and there the loser is suffixed
    # rather than overwriting anything.
    target = unique_file_name(config.data_dir, Path(file_name).stem)
    with registry.locked(registry.resolve(target)):
        try:
            info = import_file(config.data_dir, target, raw)
        except ValueError as e:
            logger.info("Refused an import of %s: %s", file_name, e)
            return _refuse_import(request, file_name, "unreadable")

    logger.info("Imported %s as %s", file_name, info.file_name)
    return RedirectResponse(
        register_url(request, selected=info.file_name, done="imported"),
        status_code=303,
    )


def _refuse_import(request: Request, file_name: str, code: str) -> Response:
    """
    Answer an import that was not taken.

    Args:
        request: The incoming request.
        file_name: The name the file arrived under, for the log.
        code: The key in :data:`IMPORT_ERRORS`.

    Returns:
        Response: A redirect back to the import form with the reason on it.
    """
    logger.info("Refused an import of %r: %s", file_name, code)
    return RedirectResponse(
        register_url(request, form=FORM_IMPORT, error=code), status_code=303
    )


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/callout", name="project_callout")
async def project_callout(
    request: Request,
    project_id: str,
    config: WebConfig = Depends(get_config),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return one project's callout: its actions, or why it has none.

    A file this application cannot read gets the warning box in place of the
    actions, with the cause in words and Download left on it, because taking a
    copy away is the one thing that still makes sense to do with it.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        config: The application's configuration.
        user: The signed-in principal.

    Returns:
        Response: The callout.

    Raises:
        ProjectNotFoundError: If the id names no file on the register.
    """
    info = _listed(config.data_dir, project_id)
    context = {
        "info": info,
        "tag": CONDITION_TAGS.get(info.condition),
        # The three conditions as three flags, rather than the enum for the
        # template to compare against: which shape of callout this is, is a
        # decision, and it belongs on this side of the line.
        "old_format": info.condition is ProjectCondition.OLD_FORMAT,
        "newer_format": info.condition is ProjectCondition.NEWER_FORMAT,
        "unreadable": info.condition is ProjectCondition.UNREADABLE,
        "open_url": project_url(request, info.file_name, "open"),
        "duplicate_url": project_url(request, info.file_name, "duplicate"),
        "download_url": project_url(request, info.file_name, "download"),
    }
    return _templates(request).TemplateResponse(
        request, "register/callout_actions.html", context
    )


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/duplicate", name="duplicate_callout")
async def duplicate_callout(
    request: Request,
    project_id: str,
    name: str = Query("", description="the name being drafted for the copy"),
    submitted: int = Query(0, description="whether the draft has been posted"),
    config: WebConfig = Depends(get_config),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return the form for copying one project without its votes.

    Args:
        request: The incoming request.
        project_id: The project to copy.
        name: The draft name for the copy, defaulting to "<name> copy".
        submitted: 1 when the draft has already been refused.
        config: The application's configuration.
        user: The signed-in principal.

    Returns:
        Response: The callout.

    Raises:
        ProjectNotFoundError: If the id names no file on the register.
    """
    info = _listed(config.data_dir, project_id)
    draft = name or f"{info.display_name} copy"
    file_name, error = _draft(config.data_dir, draft, bool(submitted))
    context = {
        "title": f"Duplicate {info.display_name} without votes",
        "label": "New name",
        "submit_label": "Duplicate",
        "action": project_url(request, info.file_name, "duplicate"),
        # Cancelling goes back to the register with this row still selected,
        # which is the actions callout it was opened from.
        "cancel_url": register_url(request, selected=info.file_name),
        "name": draft,
        "file_name": file_name,
        "directory": str(config.data_dir),
        "error": error,
        "detail": (
            f"Copies the {info.item_count} items, categories, slots and "
            "settings. No votes are copied."
        ),
    }
    return _templates(request).TemplateResponse(
        request, "register/callout_name_form.html", context
    )


@router.post(f"{PROJECTS_PREFIX}/{{project_id}}/duplicate", name="duplicate_project")
async def duplicate_project(
    request: Request,
    project_id: str,
    name: str = Form("", description="the name for the copy"),
    config: WebConfig = Depends(get_config),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Copy a project, keeping its items and dropping its votes.

    Args:
        request: The incoming request.
        project_id: The project to copy.
        name: The name for the copy, from the form.
        config: The application's configuration.
        registry: The open-project cache, for both files' locks.
        user: The signed-in principal.

    Returns:
        Response: A redirect to the register with the copy selected, or back to
        the form carrying the reason the name could not be used.

    Raises:
        ProjectNotFoundError: If the id names no file on the register, or the
            source has gone since the register drew it.
        ProjectUnreadableError: If the source will not read as a project.
        NewerFormatError: If the source was written by a newer application.
    """
    info = _listed(config.data_dir, project_id)
    trimmed = (name or "").strip()
    file_name, error = _draft(config.data_dir, trimmed, submitted=True)
    if error is not None:
        return RedirectResponse(
            register_url(
                request,
                form=FORM_DUPLICATE,
                project=info.file_name,
                name=trimmed,
                submitted=1,
            ),
            status_code=303,
        )

    # Both files. The source is read - and migrated in place, if it is in an
    # old format - and the copy is written, so neither may move underneath the
    # other half of the operation.
    with registry.locked(registry.resolve(info.file_name)):
        with registry.locked(registry.resolve(file_name)):
            try:
                copy = duplicate_project_file(
                    config.data_dir, info.file_name, trimmed
                )
            except FileNotFoundError as e:
                raise ProjectNotFoundError(str(e)) from e
            except ProjectFormatError:
                # Before the ValueError clause, and not merged into it: every
                # error in src.data.errors *is* a ValueError, so a plain
                # `except ValueError` here would turn a file from a newer
                # application into a file this one calls damaged - which is the
                # one distinction those types exist to keep.
                raise
            except ValueError as e:
                raise ProjectUnreadableError(
                    f"{info.file_name} could not be copied: {e}"
                ) from e
    logger.info("Duplicated %s as %s", info.file_name, copy.file_name)

    return RedirectResponse(
        register_url(request, selected=copy.file_name, done="duplicated"),
        status_code=303,
    )


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/download", name="download_project")
async def download_project(
    request: Request,
    project_id: str,
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Hand the project file back exactly as it is on disk.

    The whole file is read inside the lock rather than streamed after the
    handler has returned, so what arrives is one version of the file and never
    half of one and half of the next. Project files are small enough for that
    to be the simple choice as well as the correct one.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        registry: The open-project cache, for the file's lock.
        user: The signed-in principal.

    Returns:
        Response: The file, as an attachment.

    Raises:
        ProjectNotFoundError: If the id names no readable file in the data
            directory.
    """
    path = registry.resolve(project_id)
    with registry.locked(path):
        try:
            raw = path.read_bytes()
        except OSError as e:
            raise ProjectNotFoundError(f"No project file at {project_id}") from e

    # Both spellings of the name: the plain one for what reads only that, and
    # the encoded one for the project names that are not ASCII. The plain one
    # has its quotes taken out, so a file name cannot close the header field.
    fallback = path.name.encode("ascii", "replace").decode("ascii").replace('"', "")
    return Response(
        raw,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{fallback}"; '
                f"filename*=UTF-8''{quote(path.name, safe='')}"
            )
        },
    )


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/open", name="open_project")
async def open_project(
    request: Request,
    project_id: str,
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Open a project and go to its first sheet.

    **This is where the register's OK tag is actually tested.** The register
    probes the top level of a file and no further, so a file whose item entries
    are malformed, or whose ``created`` is not a date, is listed as openable and
    is not. Rather than catching that here and turning it into a condition on
    the row - which would mean deeply parsing every file on every visit to the
    register, building every project the register exists not to build - the
    failure is left to reach the damaged-file page, which names the file and
    points at the backups beside it. An old-format file is migrated on the way
    through, which is what its row said opening it would do.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A redirect to the project's first sheet.

    Raises:
        ProjectNotFoundError: If the id names no project in the directory.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file will not read as a project.
    """
    entry = registry.open(project_id)
    return RedirectResponse(
        project_url(request, entry.path.name, DEFAULT_SHEET), status_code=303
    )
