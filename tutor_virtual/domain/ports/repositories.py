"""Domain ports that must be implemented by infrastructure adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from ...shared.dto import DesignContext, DesignSessionResult
from ..converters.base import TopologyId


class DesignIterationRepository(ABC):
    """Persistence port for storing and retrieving design iterations."""

    @abstractmethod
    def save_iteration(self, result: DesignSessionResult) -> None:
        """Persist the outcome of a design session."""

    @abstractmethod
    def list_by_project(self, project_id: str) -> Iterable[DesignSessionResult]:
        """Return all iterations for a project, ordered chronologically."""

    @abstractmethod
    def get_latest(
        self,
        project_id: str,
        *,
        topology_id: Optional[TopologyId] = None,
    ) -> Optional[DesignSessionResult]:
        """Fetch the most recent iteration for the project (optionally filtered)."""


class NullDesignIterationRepository(DesignIterationRepository):
    """No-op repository useful during early development stages."""

    def save_iteration(self, result: DesignSessionResult) -> None:  # pragma: no cover - no persistence
        return

    def list_by_project(self, project_id: str) -> Iterable[DesignSessionResult]:  # pragma: no cover - no persistence
        return tuple()

    def get_latest(
        self,
        project_id: str,
        *,
        topology_id: Optional[TopologyId] = None,
    ) -> Optional[DesignSessionResult]:  # pragma: no cover - no persistence
        return None
