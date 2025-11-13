"""Orchestrates the end-to-end flow of a converter predesign session."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import List, Optional

from tutor_virtual.domain.converters.base import (
    ConverterDesigner,
    InvalidSpecificationError,
    TopologyId,
    TopologyNotSupportedError,
)
from tutor_virtual.domain.converters.factory import ConverterFactory
from tutor_virtual.domain.ports.repositories import (
    DesignIterationRepository,
    NullDesignIterationRepository,
)
from tutor_virtual.domain.validation.engine import TopologyRuleSet, ValidationEngine
from tutor_virtual.shared.dto import (
    DesignRequest,
    DesignSessionResult,
    ValidationIssue,
    ValidationSeverity,
)


class ValidationFailedError(InvalidSpecificationError):
    """Raised when blocking validation issues prevent predesign execution."""

    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues: List[ValidationIssue] = list(issues)
        message = ", ".join(issue.code for issue in self.issues) or "validation failed"
        super().__init__(message)


class DesignWorkflowService:
    """Facade that coordinates validation, design calculations and persistence."""

    def __init__(
        self,
        *,
        factory: ConverterFactory,
        validation_engine: ValidationEngine,
        repository: Optional[DesignIterationRepository] = None,
    ) -> None:
        self._factory = factory
        self._validation_engine = validation_engine
        self._repository = repository or NullDesignIterationRepository()
        self._post_run_callbacks: List[Callable[[DesignSessionResult], None]] = []

    def register_post_run_callback(
        self, callback: Callable[[DesignSessionResult], None]
    ) -> None:
        """Register a callable executed after a successful run."""

        self._post_run_callbacks.append(callback)

    def run_predesign(
        self,
        request: DesignRequest,
        *,
        ruleset_override: Optional[TopologyRuleSet] = None,
    ) -> DesignSessionResult:
        """Execute the validation and design pipeline for the given request."""

        topology_id = self._resolve_topology(request.spec.topology_id)
        designer = self._resolve_designer(topology_id)

        issues: List[ValidationIssue] = []
        issues.extend(self._validation_engine.check(request.spec, ruleset_override))
        issues.extend(designer.validate_input(request.spec))

        blocking = [issue for issue in issues if issue.severity == ValidationSeverity.ERROR]
        if blocking:
            raise ValidationFailedError(blocking)

        predesign = designer.pre_design(request.spec)
        losses = designer.estimate_losses(predesign, request.spec)
        recommendation = designer.compose_recommendation(predesign, losses, request.spec)

        context = replace(request.context, topology_id=topology_id.value)
        result = DesignSessionResult(
            context=context,
            spec=request.spec,
            predesign=predesign,
            losses=losses,
            recommendation=recommendation,
            issues=issues,
        )

        self._repository.save_iteration(result)
        for callback in self._post_run_callbacks:
            callback(result)

        return result

    def _resolve_topology(self, topology_id: str) -> TopologyId:
        try:
            return TopologyId(topology_id)
        except ValueError as exc:
            raise TopologyNotSupportedError(topology_id) from exc

    def _resolve_designer(self, topology_id: TopologyId) -> ConverterDesigner:
        return self._factory.resolve(topology_id)
