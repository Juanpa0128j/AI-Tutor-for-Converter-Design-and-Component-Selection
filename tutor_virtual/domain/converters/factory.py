"""Factory responsible for resolving converter designers by topology."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Dict, Iterable

from .base import ConverterDesigner, TopologyId, TopologyNotSupportedError

DesignerProvider = Callable[[], ConverterDesigner]


@dataclass
class TopologyInfo:
    """Metadata describing an available topology in the factory."""

    topology_id: TopologyId
    name: str
    description: str | None = None


class ConverterFactory:
    """Registry-backed factory that resolves designers on demand."""

    def __init__(self) -> None:
        self._registry: Dict[TopologyId, DesignerProvider] = {}
        self._descriptions: Dict[TopologyId, TopologyInfo] = {}

    def register(
        self,
        topology_id: TopologyId,
        provider: DesignerProvider,
        *,
        name: str | None = None,
        description: str | None = None,
        override: bool = False,
    ) -> None:
        """Register a designer provider for the given topology."""

        if not override and topology_id in self._registry:
            raise ValueError(f"Topology {topology_id} already registered")

        self._registry[topology_id] = provider
        display_name = name or topology_id.name.replace("_", " ").title()
        self._descriptions[topology_id] = TopologyInfo(
            topology_id=topology_id,
            name=display_name,
            description=description,
        )

    def resolve(self, topology_id: TopologyId) -> ConverterDesigner:
        """Return a designer instance for the requested topology."""

        try:
            provider = self._registry[topology_id]
        except KeyError as exc:  # pragma: no cover - simple guard
            raise TopologyNotSupportedError(topology_id) from exc

        return provider()

    def available_topologies(self) -> Iterable[TopologyInfo]:
        """List the metadata for registered topologies."""

        return self._descriptions.values()


def register_designer(
    factory: ConverterFactory,
    topology_id: TopologyId,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[DesignerProvider], DesignerProvider]:
    """Decorator that registers a designer provider with the factory."""

    def decorator(provider: DesignerProvider) -> DesignerProvider:
        factory.register(
            topology_id=topology_id,
            provider=provider,
            name=name,
            description=description,
        )
        return provider

    return decorator
