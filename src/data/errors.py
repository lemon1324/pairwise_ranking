"""Typed errors for the .pairrank project file format.

A project file can be wrong in ways a screen has to tell apart: the drawing
register draws one tag for a file written by a newer application than this one
and another for a file it simply cannot read. Until now the only thing
separating those cases was the word "newer" in an error message, and matching
on message text is too fragile to hang a screen on.

**Every error here subclasses :class:`ValueError`, deliberately.** The desktop
UI catches ``(OSError, ValueError)`` around each file operation and
:class:`~src.data.project_storage.ProjectStorage` documents ValueError as what
a bad file raises. Typing the errors adds a way to ask *which* kind of bad a
file is; it takes nothing away, so every existing handler keeps working
untouched.
"""

from typing import Optional


class ProjectFormatError(ValueError):
    """
    A project file cannot be used in the format version it was written in.

    This is the base of the hierarchy: catch it to mean "the file is JSON and
    is shaped like a project, but its format version is not one this code can
    work with".
    """


class NewerFormatError(ProjectFormatError):
    """
    A project file was written by a newer version of the application.

    Nothing can be done about this one locally - the file holds keys this code
    has never heard of - so the only honest recovery is to update the
    application.

    Attributes:
        file_version: The format version the file carries, or None when the
            raiser did not say.
        supported_version: The newest format version this code understands, or
            None when the raiser did not say.
    """

    def __init__(
        self,
        message: str,
        file_version: Optional[int] = None,
        supported_version: Optional[int] = None,
    ):
        """
        Initialize the error.

        Args:
            message: The message shown to the user.
            file_version: The format version the file carries.
            supported_version: The newest format version this code understands.
        """
        super().__init__(message)
        self.file_version = file_version
        self.supported_version = supported_version


class UnsupportedUpgradeError(ProjectFormatError):
    """
    No upgrade step is registered for a version on the way to the current one.

    This is a gap in the upgrade chain rather than anything wrong with the
    file, so it means a bug in this application rather than a bad file.

    Attributes:
        file_version: The version the upgrade walk got stuck at, or None when
            the raiser did not say.
    """

    def __init__(self, message: str, file_version: Optional[int] = None):
        """
        Initialize the error.

        Args:
            message: The message shown to the user.
            file_version: The version the upgrade walk got stuck at.
        """
        super().__init__(message)
        self.file_version = file_version
