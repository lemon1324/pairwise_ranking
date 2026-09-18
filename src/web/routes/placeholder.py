"""The empty sheet, drawn with nothing on it.

Scaffolding. Phase 4 builds the shell - the frame, the zones, the standard
title block, the stylesheets and the self-hosted fonts - before there is a
single screen to put on it, and a shell nobody can open is a shell nobody can
check. This route renders the shell and nothing else, so the capture harness
has a URL and the tests have something that exercises `base.html` end to end.

It is expected to be deleted once the picker, Items, Compare, Rankings and
Settings are all reachable. Nothing should come to depend on it.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from ..deps import Principal, get_current_user


router = APIRouter()

# The keys the parts-list sheets carry, as (legends, verb) pairs. Held here
# rather than in the template because the empty sheet is standing in for the
# real ones, and this is the list they will show.
SHEET_KEYS = (
    (("↑", "↓"), "select"),
    (("Pg↑↓",), "sheet"),
    (("↵",), "edit"),
    (("Esc",), "clear"),
)


@router.get("/_sheet", name="placeholder_sheet")
async def placeholder_sheet(
    request: Request, user: Principal = Depends(get_current_user)
) -> Response:
    """
    Draw an empty sheet.

    Args:
        request: The incoming request.
        user: The signed-in principal. Unused, and asked for anyway: every
            route from here on depends on it so that the day it starts reading
            a forward-auth header, no route has to be found and changed.

    Returns:
        Response: The sheet shell with an empty parts list.
    """
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {"keys": SHEET_KEYS},
    )
