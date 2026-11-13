"""Exception hierarchy. Everything the SDK raises on purpose derives from IbopError."""

from __future__ import annotations


class IbopError(Exception):
    """Base class for all SDK errors."""


class AuthenticationError(IbopError):
    """Login failed (bad credentials, changed login form) or the session could not be re-established."""


class ParseError(IbopError):
    """A response did not have the expected structure (the portal probably changed)."""


class ApiError(IbopError):
    """A module answered with an HTTP error or something that is not the expected data."""

    def __init__(self, message: str, payload: object = None) -> None:
        super().__init__(message)
        self.payload = payload


class NotFoundError(IbopError):
    """The requested customer / document is not available on this login."""
