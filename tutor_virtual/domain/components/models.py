"""Domain models for electronic components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ComponentType(str, Enum):
    """Types of electronic components."""
    
    MOSFET = "mosfet"
    DIODE = "diode"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    TRANSFORMER = "transformer"
    RESISTOR = "resistor"


@dataclass(frozen=True)
class Component:
    """Base class for electronic components."""
    
    part_number: str
    manufacturer: str
    description: str
    catalog: str  # digikey, mouser, lcsc
    price_usd: float
    availability: int  # stock quantity
    datasheet_url: Optional[str] = None
    product_url: Optional[str] = None  # Direct link to product page
    
    def __post_init__(self) -> None:
        """Validate component data."""
        if self.price_usd < 0:
            raise ValueError("Price cannot be negative")
        if self.availability < 0:
            raise ValueError("Availability cannot be negative")


@dataclass(frozen=True)
class MOSFET(Component):
    """MOSFET transistor specifications."""
    
    # Component base fields are inherited
    
    type: str = ""  # N-channel or P-channel
    vds_max: float = 0.0  # Drain-Source voltage (V)
    id_continuous: float = 0.0  # Continuous drain current (A)
    id_pulsed: float = 0.0  # Pulsed drain current (A)
    rds_on: float = 0.0  # On-resistance (Ω)
    vgs_threshold: float = 0.0  # Gate threshold voltage (V)
    qg_total: float = 0.0  # Total gate charge (nC)
    package: str = "TO-220"  # TO-220, DPAK, etc.
    
    def power_loss(self, current: float) -> float:
        """Calculate conduction loss at given current."""
        return current ** 2 * self.rds_on


@dataclass(frozen=True)
class Diode(Component):
    """Diode specifications."""
    
    type: str = ""  # Schottky, Fast Recovery, Standard, etc.
    vrrm: float = 0.0  # Repetitive reverse voltage (V)
    if_avg: float = 0.0  # Average forward current (A)
    vf: float = 0.0  # Forward voltage drop (V)
    trr: Optional[float] = None  # Reverse recovery time (ns)
    package: str = "DO-201"
    
    def power_loss(self, current: float) -> float:
        """Calculate forward conduction loss."""
        return self.vf * current


@dataclass(frozen=True)
class Capacitor(Component):
    """Capacitor specifications."""
    
    capacitance: float = 0.0  # Capacitance (F)
    voltage_rating: float = 0.0  # Voltage rating (V)
    tolerance: float = 0.0  # Tolerance (%)
    dielectric: str = ""  # Ceramic, Electrolytic, Film, etc.
    esr: Optional[float] = None  # Equivalent series resistance (Ω)
    ripple_current: Optional[float] = None  # Ripple current rating (A)
    package: str = "0805"


@dataclass(frozen=True)
class Inductor(Component):
    """Inductor specifications."""
    
    inductance: float = 0.0  # Inductance (H)
    current_rating: float = 0.0  # Current rating (A)
    dcr: float = 0.0  # DC resistance (Ω)
    saturation_current: float = 0.0  # Saturation current (A)
    package: str = "TH"  # Through-hole or SMD package
    core_material: Optional[str] = None


@dataclass(frozen=True)
class ComponentRequirements:
    """Requirements for component selection derived from predesign."""
    
    component_type: ComponentType
    
    # Voltage requirements
    voltage_max: Optional[float] = None
    voltage_min: Optional[float] = None
    
    # Current requirements
    current_max: Optional[float] = None
    current_avg: Optional[float] = None
    current_rms: Optional[float] = None
    
    # Power requirements
    power_dissipation: Optional[float] = None
    
    # Specific requirements for different component types
    # For capacitors
    capacitance_min: Optional[float] = None
    capacitance_max: Optional[float] = None
    ripple_current_min: Optional[float] = None
    
    # For inductors
    inductance_min: Optional[float] = None
    inductance_max: Optional[float] = None
    
    # For MOSFETs
    rds_on_max: Optional[float] = None
    gate_charge_max: Optional[float] = None
    
    # For diodes
    reverse_recovery_max: Optional[float] = None
    forward_voltage_max: Optional[float] = None
    
    # Package preferences
    preferred_packages: Optional[list[str]] = None
    
    # Safety margins
    voltage_margin: float = 1.5  # 50% margin
    current_margin: float = 1.25  # 25% margin
