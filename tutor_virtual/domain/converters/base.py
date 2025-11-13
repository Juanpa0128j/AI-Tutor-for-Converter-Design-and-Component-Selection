"""Base contracts for converter designers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import List

from ...shared.dto import (
    ConverterSpec,
    DesignRecommendation,
    LossReport,
    PreDesignResult,
    ValidationIssue,
)


class TopologyId(str, Enum):
    """Canonical identifiers for supported converter topologies."""

    AC_DC_RECTIFIER_SINGLE = "ac_dc_rectifier_single"
    AC_DC_RECTIFIER_FULL = "ac_dc_rectifier_full"
    AC_DC_RECTIFIER_THREE_PHASE = "ac_dc_rectifier_three_phase"
    AC_AC_TRIAC = "ac_ac_triac"
    DC_DC_BUCK = "dc_dc_buck"
    DC_DC_BOOST = "dc_dc_boost"
    DC_DC_BUCK_BOOST = "dc_dc_buck_boost"
    DC_DC_CUK = "dc_dc_cuk"
    DC_DC_FLYBACK = "dc_dc_flyback"
    DC_AC_HALF_BRIDGE = "dc_ac_half_bridge"
    DC_AC_FULL_BRIDGE_SINGLE = "dc_ac_full_bridge_single"
    DC_AC_FULL_BRIDGE_THREE = "dc_ac_full_bridge_three"
    DC_AC_MODULATION = "dc_ac_modulation"
    UNKNOWN = "unknown"


class InvalidSpecificationError(ValueError):
    """Raised when the provided specification does not meet basic criteria."""


class TopologyNotSupportedError(LookupError):
    """Raised when the factory cannot resolve a designer for the topology."""


class DesignComputationError(RuntimeError):
    """Raised when a designer cannot produce results for the specification."""


class ConverterDesigner(ABC):
    """Defines the lifecycle of a converter predesign computation."""

    topology_id: TopologyId

    @abstractmethod
    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        """Perform topology-specific validation on the provided spec."""

    @abstractmethod
    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        """Calculate the primary component values for the converter."""

    @abstractmethod
    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        """Estimate switching, conduction and auxiliary losses."""

    @abstractmethod
    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        """Build the final recommendation delivered to the user."""
