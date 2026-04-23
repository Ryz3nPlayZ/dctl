from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXIT_CODES = {
    "UNKNOWN": 1,
    "ELEMENT_NOT_FOUND": 2,
    "MULTIPLE_MATCHES": 3,
    "ACTION_NOT_SUPPORTED": 4,
    "PERMISSION_DENIED": 5,
    "DEPENDENCY_MISSING": 6,
    "PLATFORM_NOT_SUPPORTED": 7,
    "TIMEOUT": 8,
    "INVALID_SELECTOR": 9,
    "CAPABILITY_UNAVAILABLE": 10,
    "BACKEND_FAILURE": 11,
}


@dataclass(slots=True)
class DctlError(Exception):
    code: str
    message: str
    suggestion: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES.get(self.code, 1)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "code": self.code,
            "message": self.message,
        }
        if self.suggestion:
            data["suggestion"] = self.suggestion
        if self.details:
            data["details"] = self.details
        return data


def as_dctl_error(exc: Exception) -> DctlError:
    if isinstance(exc, DctlError):
        return exc
    return DctlError("UNKNOWN", str(exc) or exc.__class__.__name__)

