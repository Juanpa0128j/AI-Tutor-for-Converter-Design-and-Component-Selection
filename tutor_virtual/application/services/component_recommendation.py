"""Component recommendation service."""

from __future__ import annotations

import hashlib
from typing import List, Optional

from tutor_virtual.domain.components import (
    ComponentRequirements,
    ComponentSelector,
    ComponentType,
    PrioritizationWeights,
)
from tutor_virtual.domain.components.selector import ComponentScore
from tutor_virtual.domain.ports import ComponentCatalogPort, ComponentRepositoryPort
from tutor_virtual.shared.dto import PreDesignResult


class ComponentRecommendationService:
    """Service for intelligent component recommendation."""
    
    def __init__(
        self,
        catalogs: List[ComponentCatalogPort],
        cache: Optional[ComponentRepositoryPort] = None,
        default_weights: Optional[PrioritizationWeights] = None
    ):
        """
        Initialize recommendation service.
        
        Args:
            catalogs: List of catalog adapters (DigiKey, Mouser, LCSC)
            cache: Optional cache repository for component data
            default_weights: Default prioritization weights
        """
        self.catalogs = catalogs
        self.cache = cache
        self.selector = ComponentSelector(default_weights)
    
    async def recommend_components(
        self,
        predesign_result: PreDesignResult,
        component_type: ComponentType,
        weights: Optional[PrioritizationWeights] = None,
        top_n: int = 5
    ) -> List[ComponentScore]:
        """
        Recommend components based on predesign results.
        
        Args:
            predesign_result: Results from converter predesign
            component_type: Type of component to recommend
            weights: Custom prioritization weights (optional)
            top_n: Number of top recommendations to return
            
        Returns:
            List of scored and ranked components
        """
        # Update selector weights if custom weights provided
        if weights:
            self.selector = ComponentSelector(weights)
        
        # Extract requirements from predesign
        requirements = self._extract_requirements(predesign_result, component_type)
        
        # Generate cache key
        cache_key = self._generate_cache_key(requirements)
        
        # Try to get from cache first
        all_components = []
        if self.cache:
            cached = await self.cache.get_cached_components(cache_key)
            if cached:
                all_components = cached
        
        # If not in cache, search all catalogs
        if not all_components:
            for catalog in self.catalogs:
                try:
                    components = await catalog.search_components(requirements)
                    all_components.extend(components)
                except Exception as e:
                    # Log error but continue with other catalogs
                    print(f"Error searching {catalog.get_catalog_name()}: {e}")
            
            # Cache the results
            if self.cache and all_components:
                await self.cache.cache_components(cache_key, all_components)
        
        # Select top components using prioritization algorithm
        top_components = self.selector.select_top_components(
            all_components,
            requirements,
            top_n
        )
        
        return top_components
    
    def _extract_requirements(
        self,
        predesign: PreDesignResult,
        component_type: ComponentType
    ) -> ComponentRequirements:
        """Extract component requirements from predesign results."""
        primary = predesign.primary_values
        
        # Base requirements
        requirements = ComponentRequirements(component_type=component_type)
        
        # Extract common electrical parameters
        voltage_max = None
        current_max = None
        
        # Try to get voltage from common parameter names
        for key in ["vo_avg", "vout", "vo_target", "vdc", "vo_rms"]:
            if key in primary:
                voltage_max = primary[key]
                break
        
        # Try to get current from common parameter names
        for key in ["io_max", "io_avg", "il_avg", "il_max"]:
            if key in primary:
                current_max = primary[key]
                break
        
        # Component-specific requirements
        if component_type == ComponentType.MOSFET:
            return ComponentRequirements(
                component_type=component_type,
                voltage_max=voltage_max,
                current_max=current_max,
                current_avg=primary.get("io_avg"),
                rds_on_max=primary.get("rds_on_max"),
                voltage_margin=1.5,
                current_margin=1.25
            )
        
        elif component_type == ComponentType.DIODE:
            return ComponentRequirements(
                component_type=component_type,
                voltage_max=voltage_max or primary.get("piv"),
                current_avg=primary.get("io_avg"),
                forward_voltage_max=1.0,  # Typical max Vf
                voltage_margin=1.5,
                current_margin=1.25
            )
        
        elif component_type == ComponentType.CAPACITOR:
            return ComponentRequirements(
                component_type=component_type,
                voltage_max=voltage_max,
                capacitance_min=primary.get("required_capacitance") or primary.get("capacitance"),
                ripple_current_min=primary.get("delta_il"),
                voltage_margin=1.5
            )
        
        elif component_type == ComponentType.INDUCTOR:
            return ComponentRequirements(
                component_type=component_type,
                inductance_min=primary.get("inductance") or primary.get("l_min"),
                current_max=current_max,
                current_margin=1.25
            )
        
        return requirements
    
    def _generate_cache_key(self, requirements: ComponentRequirements) -> str:
        """Generate unique cache key for component requirements."""
        # Create a string representation of requirements
        req_str = f"{requirements.component_type.value}"
        
        if requirements.voltage_max:
            req_str += f":v{requirements.voltage_max}"
        if requirements.current_max:
            req_str += f":i{requirements.current_max}"
        if requirements.capacitance_min:
            req_str += f":c{requirements.capacitance_min}"
        if requirements.inductance_min:
            req_str += f":l{requirements.inductance_min}"
        
        # Hash to create shorter key
        hash_obj = hashlib.md5(req_str.encode())
        return f"component:{hash_obj.hexdigest()}"
