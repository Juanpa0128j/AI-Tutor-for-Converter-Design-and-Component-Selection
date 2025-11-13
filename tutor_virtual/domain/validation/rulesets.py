"""Default validation rulesets derived from converter design restrictions."""

from __future__ import annotations

from math import sqrt
from typing import Dict, Tuple

from ...shared.dto import ConverterSpec, ValidationSeverity
from ..converters.base import TopologyId
from .engine import TopologyRuleSet, ValidationEngine, ValidationRule


def _optional_numeric(spec: ConverterSpec, key: str) -> float | None:
    value = spec.operating_conditions.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _constraint_numeric(spec: ConverterSpec, key: str) -> float | None:
    value = spec.constraints.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _rule(code: str, message: str, func) -> ValidationRule:
    def evaluator(spec: ConverterSpec) -> Tuple[bool, Dict[str, float | str]]:
        try:
            passed, details = func(spec)
        except Exception as exc:  # pragma: no cover - defensive
            return False, {"error": str(exc)}
        return passed, details

    return ValidationRule(code=code, message=message, severity=ValidationSeverity.ERROR, evaluator=evaluator)


def _warning(code: str, message: str, func) -> ValidationRule:
    def evaluator(spec: ConverterSpec) -> Tuple[bool, Dict[str, float | str]]:
        try:
            passed, details = func(spec)
        except Exception as exc:  # pragma: no cover - defensive
            return False, {"error": str(exc)}
        return passed, details

    return ValidationRule(code=code, message=message, severity=ValidationSeverity.WARNING, evaluator=evaluator)


def _buck_rules() -> list[ValidationRule]:
    def duty_within_bounds(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        vin = _optional_numeric(spec, "vin")
        vo = _optional_numeric(spec, "vo_target")
        if vin is None or vo is None:
            return True, {}
        duty = vo / vin
        return 0.0 < duty < 1.0, {"duty": duty}

    def ripple_limit(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        ripple_pct = spec.operating_conditions.get("delta_il_pct")
        if ripple_pct is None:
            return True, {}
        return float(ripple_pct) <= 60.0, {"delta_il_pct": float(ripple_pct)}

    return [
        _rule("buck_duty_range", "Buck duty cycle must be between 0 and 1", duty_within_bounds),
        _warning("buck_delta_il", "Inductor ripple percentage is high for CCM", ripple_limit),
    ]


def _boost_rules() -> list[ValidationRule]:
    def voltage_relation(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        vin = _optional_numeric(spec, "vin")
        vo = _optional_numeric(spec, "vo_target")
        if vin is None or vo is None:
            return True, {}
        return vo > vin, {"vin": vin, "vo": vo}

    def duty_headroom(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        vin = _optional_numeric(spec, "vin")
        vo = _optional_numeric(spec, "vo_target")
        if vin is None or vo is None:
            return True, {}
        duty = 1.0 - vin / vo
        return duty < 0.9, {"duty": duty}

    return [
        _rule("boost_vo_gt_vin", "Boost output voltage must exceed input voltage", voltage_relation),
        _warning("boost_duty", "Boost duty cycle close to unity", duty_headroom),
    ]


def _buck_boost_rules() -> list[ValidationRule]:
    def polarity(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        vo = _optional_numeric(spec, "vo_target")
        if vo is None:
            return True, {}
        return vo < 0.0, {"vo_target": vo}

    return [_rule("buck_boost_polarity", "Buck-boost output should be negative relative to input", polarity)]


def _cuk_rules() -> list[ValidationRule]:
    def high_ripple(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        ripple = spec.operating_conditions.get("delta_vo_pct")
        if ripple is None:
            return True, {}
        return float(ripple) <= 5.0, {"delta_vo_pct": float(ripple)}

    return [_warning("cuk_delta_vo", "Ćuk converter ripple target is high", high_ripple)]


def _flyback_rules() -> list[ValidationRule]:
    def duty_limit(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        duty_max = _optional_numeric(spec, "duty_max")
        if duty_max is None:
            return True, {}
        return duty_max < 0.5, {"duty_max": duty_max}

    def reset_margin(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        turns = _optional_numeric(spec, "turns_ratio")
        vin_max = _optional_numeric(spec, "vin_max")
        vo = _optional_numeric(spec, "vo_target")
        if turns is None or vin_max is None or vo is None:
            return True, {}
        v_reset = turns * vo
        margin = vin_max + v_reset
        return margin < 2.0 * vin_max + v_reset, {"vin_max": vin_max, "v_reset": v_reset}

    return [
        _rule("flyback_duty", "Flyback maximum duty should remain below 0.5", duty_limit),
        _warning("flyback_reset", "Flyback reset voltage is approaching switch limit", reset_margin),
    ]


def _rectifier_rules(single_phase: bool) -> list[ValidationRule]:
    def piv_requirement(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        vac = _optional_numeric(spec, "vac_rms")
        vll = _optional_numeric(spec, "vll_rms")
        load_r = _optional_numeric(spec, "load_resistance")
        rating = _constraint_numeric(spec, "diode_piv_rating")
        if rating is None:
            return True, {}
        if single_phase:
            if vac is None:
                return True, {}
            required = sqrt(2.0) * vac if spec.topology_id.endswith("single") else 2.0 * sqrt(2.0) * vac
        else:
            if vll is None:
                return True, {}
            required = 1.155 * sqrt(2.0) * vll
        return rating >= required, {"piv_rating": rating, "piv_required": required}

    return [_warning("rectifier_piv", "Diode PIV rating near theoretical minimum", piv_requirement)]


def _triac_rules() -> list[ValidationRule]:
    def angle_range(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        alpha = _optional_numeric(spec, "alpha_deg")
        if alpha is None:
            return True, {}
        return 0.0 <= alpha <= 180.0, {"alpha_deg": alpha}

    return [_rule("triac_alpha", "Trigger angle must be between 0 and 180 degrees", angle_range)]


def _inverter_rules(single_phase: bool) -> list[ValidationRule]:
    def modulation_limit(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        ma = _optional_numeric(spec, "modulation_index")
        if ma is None:
            return True, {}
        return 0.0 <= ma <= (1.15 if not single_phase else 1.0), {"modulation_index": ma}

    return [_warning("inverter_ma", "Modulation index exceeds linear region", modulation_limit)]


def _modulation_rules() -> list[ValidationRule]:
    def carrier_ratio(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        fc = _optional_numeric(spec, "carrier_freq")
        fo = _optional_numeric(spec, "fundamental_freq")
        if fc is None or fo is None or fo == 0:
            return True, {}
        ratio = fc / fo
        return ratio >= 15.0, {"m_f": ratio}

    def ma_bound(spec: ConverterSpec) -> Tuple[bool, Dict[str, float]]:
        ma = _optional_numeric(spec, "modulation_index")
        if ma is None:
            return True, {}
        return ma <= 1.15, {"modulation_index": ma}

    return [
        _rule("modulation_ratio", "Carrier to fundamental ratio must be >= 15", carrier_ratio),
        _warning("modulation_ma", "Modulation index approaching overmodulation", ma_bound),
    ]


def register_default_rules(validation_engine: ValidationEngine) -> None:
    """Populate the validation engine with default rulesets."""

    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_DC_BUCK,
            version="1.0",
            rules=_buck_rules(),
            metadata={"source": "IEEE/IEC derived constraints"},
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_DC_BOOST,
            version="1.0",
            rules=_boost_rules(),
            metadata={"source": "IEEE/IEC derived constraints"},
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_DC_BUCK_BOOST,
            version="1.0",
            rules=_buck_boost_rules(),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_DC_CUK,
            version="1.0",
            rules=_cuk_rules(),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_DC_FLYBACK,
            version="1.0",
            rules=_flyback_rules(),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.AC_DC_RECTIFIER_SINGLE,
            version="1.0",
            rules=_rectifier_rules(single_phase=True),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.AC_DC_RECTIFIER_FULL,
            version="1.0",
            rules=_rectifier_rules(single_phase=True),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.AC_DC_RECTIFIER_THREE_PHASE,
            version="1.0",
            rules=_rectifier_rules(single_phase=False),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.AC_AC_TRIAC,
            version="1.0",
            rules=_triac_rules(),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_AC_HALF_BRIDGE,
            version="1.0",
            rules=_inverter_rules(single_phase=True),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_AC_FULL_BRIDGE_SINGLE,
            version="1.0",
            rules=_inverter_rules(single_phase=True),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_AC_FULL_BRIDGE_THREE,
            version="1.0",
            rules=_inverter_rules(single_phase=False),
        )
    )
    validation_engine.register_ruleset(
        TopologyRuleSet(
            topology_id=TopologyId.DC_AC_MODULATION,
            version="1.0",
            rules=_modulation_rules(),
        )
    )