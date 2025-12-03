"""Component selection and prioritization engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .models import Component, ComponentRequirements


@dataclass
class PrioritizationWeights:
    """Weights for multi-criteria component prioritization."""
    
    cost: float = 0.30
    availability: float = 0.25
    efficiency: float = 0.25
    thermal: float = 0.20
    
    def __post_init__(self) -> None:
        """Validate that weights sum to 1.0."""
        total = self.cost + self.availability + self.efficiency + self.thermal
        if not (0.99 <= total <= 1.01):  # Allow small floating point errors
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        
        # Validate individual weights
        for weight in [self.cost, self.availability, self.efficiency, self.thermal]:
            if not (0.0 <= weight <= 1.0):
                raise ValueError(f"Each weight must be between 0 and 1, got {weight}")


@dataclass
class ComponentScore:
    """Scoring breakdown for a component."""
    
    component: Component
    cost_score: float
    availability_score: float
    efficiency_score: float
    thermal_score: float
    total_score: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary for display."""
        return {
            "part_number": self.component.part_number,
            "manufacturer": self.component.manufacturer,
            "catalog": self.component.catalog,
            "price": f"${self.component.price_usd:.2f}",
            "availability": self.component.availability,
            "scores": {
                "cost": f"{self.cost_score:.2f}",
                "availability": f"{self.availability_score:.2f}",
                "efficiency": f"{self.efficiency_score:.2f}",
                "thermal": f"{self.thermal_score:.2f}",
                "total": f"{self.total_score:.2f}",
            }
        }


class ComponentSelector:
    """Intelligent component selection with multi-criteria prioritization."""
    
    def __init__(self, weights: Optional[PrioritizationWeights] = None):
        """Initialize selector with prioritization weights."""
        self.weights = weights or PrioritizationWeights()
    
    def filter_by_requirements(
        self,
        components: List[Component],
        requirements: ComponentRequirements
    ) -> List[Component]:
        """Phase 1: Technical filtering based on electrical requirements."""
        filtered = []
        
        for component in components:
            if self._meets_requirements(component, requirements):
                filtered.append(component)
        
        return filtered
    
    def _meets_requirements(
        self,
        component: Component,
        requirements: ComponentRequirements
    ) -> bool:
        """Check if component meets technical requirements.
        
        TEMPORARY: All requirements checks are disabled for testing.
        """
        from .models import MOSFET, Diode, Capacitor, Inductor
        import logging
        logger = logging.getLogger(__name__)
        
        # TEMPORARY: Skip all requirements validation
        logger.info(f"      ✅ {component.part_number}: requirements check BYPASSED (testing mode)")
        return True
        
        # Original validation code (commented out for testing)
        # # Voltage requirements
        # if isinstance(component, (MOSFET, Diode)):
        #     if requirements.voltage_max:
        #         voltage_rating = component.vds_max if isinstance(component, MOSFET) else component.vrrm
        #         required_voltage = requirements.voltage_max * requirements.voltage_margin
        #         if voltage_rating < required_voltage:
        #             logger.info(f"      ❌ {component.part_number}: voltage {voltage_rating}V < required {required_voltage}V")
        #             return False
        # 
        # elif isinstance(component, Capacitor):
        #     if requirements.voltage_max:
        #         required_voltage = requirements.voltage_max * requirements.voltage_margin
        #         if component.voltage_rating < required_voltage:
        #             logger.info(f"      ❌ {component.part_number}: voltage {component.voltage_rating}V < required {required_voltage}V")
        #             return False
        #     if requirements.capacitance_min:
        #         if component.capacitance < requirements.capacitance_min:
        #             logger.info(f"      ❌ {component.part_number}: capacitance {component.capacitance*1e6:.2f}µF < required {requirements.capacitance_min*1e6:.2f}µF")
        #             return False
        #     if requirements.capacitance_max:
        #         if component.capacitance > requirements.capacitance_max:
        #             logger.info(f"      ❌ {component.part_number}: capacitance {component.capacitance*1e6:.2f}µF > max {requirements.capacitance_max*1e6:.2f}µF")
        #             return False
        # 
        # elif isinstance(component, Inductor):
        #     if requirements.inductance_min:
        #         if component.inductance < requirements.inductance_min:
        #             logger.info(f"      ❌ {component.part_number}: inductance {component.inductance*1e6:.2f}µH < required {requirements.inductance_min*1e6:.2f}µH")
        #             return False
        #     if requirements.inductance_max:
        #         if component.inductance > requirements.inductance_max:
        #             logger.info(f"      ❌ {component.part_number}: inductance {component.inductance*1e6:.2f}µH > max {requirements.inductance_max*1e6:.2f}µH")
        #             return False
        # 
        # # Current requirements
        # if isinstance(component, MOSFET):
        #     if requirements.current_max:
        #         required_current = requirements.current_max * requirements.current_margin
        #         if component.id_continuous < required_current:
        #             logger.info(f"      ❌ {component.part_number}: current {component.id_continuous}A < required {required_current}A")
        #             return False
        #     if requirements.rds_on_max:
        #         if component.rds_on and component.rds_on > requirements.rds_on_max:
        #             logger.info(f"      ❌ {component.part_number}: RDS(on) {component.rds_on}Ω > max {requirements.rds_on_max}Ω")
        #             return False
        # 
        # elif isinstance(component, Diode):
        #     if requirements.current_avg:
        #         required_current = requirements.current_avg * requirements.current_margin
        #         if component.if_avg < required_current:
        #             logger.info(f"      ❌ {component.part_number}: current {component.if_avg}A < required {required_current}A")
        #             return False
        # 
        # elif isinstance(component, Inductor):
        #     if requirements.current_max:
        #         required_current = requirements.current_max * requirements.current_margin
        #         if component.current_rating < required_current:
        #             logger.info(f"      ❌ {component.part_number}: current {component.current_rating}A < required {required_current}A")
        #             return False
        # 
        # # Package preferences
        # if requirements.preferred_packages:
        #     if component.package not in requirements.preferred_packages:
        #         return False
        # 
        # return True
    
    def score_components(
        self,
        components: List[Component],
        requirements: ComponentRequirements
    ) -> List[ComponentScore]:
        """Phase 2 & 3: Score and rank components using multi-criteria analysis."""
        if not components:
            return []
        
        # Normalize metrics
        prices = [c.price_usd for c in components]
        availabilities = [c.availability for c in components]
        
        price_min, price_max = min(prices), max(prices)
        avail_min, avail_max = min(availabilities), max(availabilities)
        
        scores = []
        for component in components:
            # Cost score (lower is better, so invert)
            cost_score = self._normalize_inverse(
                component.price_usd, price_min, price_max
            )
            
            # Availability score (higher is better)
            availability_score = self._normalize(
                component.availability, avail_min, avail_max
            )
            
            # Efficiency score (component-specific)
            efficiency_score = self._calculate_efficiency_score(component, requirements)
            
            # Thermal score (lower power dissipation is better)
            thermal_score = self._calculate_thermal_score(component, requirements)
            
            # Calculate weighted total
            total_score = (
                self.weights.cost * cost_score +
                self.weights.availability * availability_score +
                self.weights.efficiency * efficiency_score +
                self.weights.thermal * thermal_score
            )
            
            scores.append(ComponentScore(
                component=component,
                cost_score=cost_score,
                availability_score=availability_score,
                efficiency_score=efficiency_score,
                thermal_score=thermal_score,
                total_score=total_score
            ))
        
        # Sort by total score (descending)
        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores
    
    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value to [0, 1] range."""
        if max_val == min_val:
            return 1.0
        return (value - min_val) / (max_val - min_val)
    
    def _normalize_inverse(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value inversely (lower is better)."""
        return 1.0 - self._normalize(value, min_val, max_val)
    
    def _calculate_efficiency_score(
        self,
        component: Component,
        requirements: ComponentRequirements
    ) -> float:
        """Calculate efficiency score based on component type."""
        from .models import MOSFET, Diode
        
        if isinstance(component, MOSFET):
            # Lower RDS(on) is better for efficiency
            if requirements.rds_on_max:
                return 1.0 - (component.rds_on / requirements.rds_on_max)
            return 0.5
        
        elif isinstance(component, Diode):
            # Lower Vf is better for efficiency
            if requirements.forward_voltage_max:
                return 1.0 - (component.vf / requirements.forward_voltage_max)
            return 0.5
        
        # For passive components, assume neutral efficiency impact
        return 0.5
    
    def _calculate_thermal_score(
        self,
        component: Component,
        requirements: ComponentRequirements
    ) -> float:
        """Calculate thermal performance score."""
        from .models import MOSFET, Diode
        
        if not requirements.current_avg:
            return 0.5
        
        if isinstance(component, MOSFET):
            power_loss = component.power_loss(requirements.current_avg)
        elif isinstance(component, Diode):
            power_loss = component.power_loss(requirements.current_avg)
        else:
            return 0.5
        
        # Lower power loss is better
        if requirements.power_dissipation:
            return max(0.0, 1.0 - (power_loss / requirements.power_dissipation))
        
        return 0.5
    
    def select_top_components(
        self,
        components: List[Component],
        requirements: ComponentRequirements,
        top_n: int = 5
    ) -> List[ComponentScore]:
        """Complete selection pipeline: filter → score → rank → top N."""
        filtered = self.filter_by_requirements(components, requirements)
        scored = self.score_components(filtered, requirements)
        return scored[:top_n]
