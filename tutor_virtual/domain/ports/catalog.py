"""Port interfaces for component catalog integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from tutor_virtual.domain.components import Component, ComponentRequirements


class ComponentCatalogPort(ABC):
    """Interface for external component catalog APIs."""
    
    @abstractmethod
    async def search_components(
        self,
        requirements: ComponentRequirements,
        limit: int = 100
    ) -> List[Component]:
        """Search for components matching requirements."""
        pass
    
    @abstractmethod
    async def get_component_details(self, part_number: str) -> Optional[Component]:
        """Get detailed specifications for a specific part number."""
        pass
    
    @abstractmethod
    def get_catalog_name(self) -> str:
        """Return the name of this catalog (digikey, mouser, lcsc)."""
        pass


class ComponentRepositoryPort(ABC):
    """Interface for component data persistence and caching."""
    
    @abstractmethod
    async def get_cached_components(
        self,
        cache_key: str
    ) -> Optional[List[Component]]:
        """Retrieve cached component search results."""
        pass
    
    @abstractmethod
    async def cache_components(
        self,
        cache_key: str,
        components: List[Component],
        ttl_seconds: int = 86400
    ) -> None:
        """Cache component search results."""
        pass
    
    @abstractmethod
    async def invalidate_cache(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern."""
        pass
