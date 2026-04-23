from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DesktopBackend(ABC):
    @abstractmethod
    def capabilities(self) -> dict[str, Any]: ...

    @abstractmethod
    def doctor(self) -> dict[str, Any]: ...

