"""Validation engine responsible for enforcing topology rules."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from ...shared.dto import ConverterSpec, ValidationIssue, ValidationSeverity
from ..converters.base import TopologyId, InvalidSpecificationError


class RuleEvaluator(Protocol):
    """Callable signature used to evaluate a validation rule."""

    def __call__(self, spec: ConverterSpec) -> tuple[bool, Dict[str, float | str]]:  # pragma: no cover - structural
        ...


@dataclass(slots=True)
class ValidationRule:
    """Representation of a single validation rule tied to a topology."""

    code: str
    message: str
    severity: ValidationSeverity
    evaluator: RuleEvaluator


@dataclass(slots=True)
class TopologyRuleSet:
    """Group of rules associated with a particular topology and version."""

    topology_id: TopologyId
    version: str
    rules: Iterable[ValidationRule] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


class ValidationEngine:
    """Central coordinator that evaluates rules over converter specs."""

    def __init__(self) -> None:
        self._rulesets: Dict[TopologyId, TopologyRuleSet] = {}

    def register_ruleset(self, rule_set: TopologyRuleSet, *, override: bool = False) -> None:
        """Register the rule set for a topology."""

        if not override and rule_set.topology_id in self._rulesets:
            raise ValueError(f"Ruleset for {rule_set.topology_id} already registered")

        self._rulesets[rule_set.topology_id] = rule_set

    def check(self, spec: ConverterSpec, topology_ruleset: Optional[TopologyRuleSet] = None) -> List[ValidationIssue]:
        """Evaluate all applicable rules and collect issues."""

        if topology_ruleset is None:
            try:
                topology_ruleset = self._rulesets[TopologyId(spec.topology_id)]
            except (KeyError, ValueError) as exc:
                raise InvalidSpecificationError(f"Unknown topology: {spec.topology_id}") from exc

        issues: List[ValidationIssue] = []
        for rule in topology_ruleset.rules:
            passed, details = rule.evaluator(spec)
            if passed:
                continue
            issues.append(
                ValidationIssue(
                    code=rule.code,
                    message=rule.message,
                    severity=rule.severity,
                    details=details,
                )
            )
        return issues

    def get_ruleset(self, topology_id: TopologyId) -> TopologyRuleSet:
        """Retrieve the registered ruleset for a topology."""

        try:
            return self._rulesets[topology_id]
        except KeyError as exc:  # pragma: no cover - simple guard
            raise InvalidSpecificationError(f"No ruleset registered for {topology_id}") from exc
