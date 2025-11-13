"""Shared data transfer objects for the design workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Mapping, Optional


class ValidationSeverity(str, Enum):
    """Severity levels returned by the validation engine."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(slots=True)
class ValidationIssue:
    """Represents a rule violation or advisory detected during validation."""

    code: str
    message: str
    severity: ValidationSeverity
    details: Mapping[str, float | str] = field(default_factory=dict)


@dataclass(slots=True)
class DesignContext:
    """Holds contextual identifiers for the current design session."""

    user_id: Optional[str]
    project_id: Optional[str]
    iteration_id: Optional[str] = None
    topology_id: Optional[str] = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ConverterSpec:
    """Normalized specification and constraints provided by the user."""

    topology_id: str
    operating_conditions: Mapping[str, float]
    constraints: Mapping[str, float] = field(default_factory=dict)
    design_goals: Mapping[str, float | str] = field(default_factory=dict)
    notes: Optional[str] = None


@dataclass(slots=True)
class DesignRequest:
    """Request envelope provided by the presentation layer."""

    context: DesignContext
    spec: ConverterSpec


@dataclass(slots=True)
class PreDesignResult:
    """Primary component values and intermediate calculations."""

    primary_values: Dict[str, float]
    operating_mode: Optional[str] = None
    assumptions: Mapping[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LossReport:
    """Aggregated losses and thermal metrics estimated by the designer."""

    totals: Dict[str, float]
    per_element: Mapping[str, float] = field(default_factory=dict)
    temperature_rise: Optional[float] = None


@dataclass(slots=True)
class DesignRecommendation:
    """Final recommendation delivered to the user."""

    summary: str
    suggested_adjustments: Mapping[str, str] = field(default_factory=dict)
    next_steps: List[str] = field(default_factory=list)
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DesignSessionResult:
    """Outcome of the predesign workflow for a converter."""

    context: DesignContext
    spec: ConverterSpec
    predesign: PreDesignResult
    losses: LossReport
    recommendation: DesignRecommendation
    issues: List[ValidationIssue] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
