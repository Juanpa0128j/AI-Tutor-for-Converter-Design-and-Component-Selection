"""Concrete converter designer implementations per topology."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt
from typing import Dict, List

from ...shared.dto import (
    ConverterSpec,
    DesignRecommendation,
    LossReport,
    PreDesignResult,
    ValidationIssue,
    ValidationSeverity,
)
from .base import ConverterDesigner, TopologyId
from .factory import ConverterFactory
from .utils import (
    capacitor_ripple_current,
    cos_deg,
    ensure_keys,
    get_optional,
    percentage_to_fraction,
    require,
    rms_from_peak,
    sin_deg,
    triangular_rms,
)


def _missing_issues(spec: ConverterSpec, *keys: str) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for key in ensure_keys(spec, *keys):
        issues.append(
            ValidationIssue(
                code=f"missing_{key}",
                message=f"Specification missing required value '{key}'",
                severity=ValidationSeverity.ERROR,
            )
        )
    return issues


def _positive_issue(spec: ConverterSpec, key: str) -> ValidationIssue:
    return ValidationIssue(
        code=f"invalid_{key}",
        message=f"Specification value '{key}' must be positive",
        severity=ValidationSeverity.ERROR,
    )


class HalfWaveRectifierDesigner(ConverterDesigner):
    topology_id = TopologyId.AC_DC_RECTIFIER_SINGLE

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "vac_rms", "freq_ac", "load_resistance")
        for key in ("vac_rms", "freq_ac", "load_resistance"):
            if key not in spec.operating_conditions:
                continue
            if spec.operating_conditions[key] <= 0:
                issues.append(_positive_issue(spec, key))
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vac_rms = require(spec, "vac_rms")
        freq = require(spec, "freq_ac")
        load_r = require(spec, "load_resistance")
        diode_drop = get_optional(spec, "diode_drop", 0.7)
        ripple_pct = spec.constraints.get("voltage_ripple_pct", 5.0)
        ripple_fraction = percentage_to_fraction(ripple_pct)

        vm = sqrt(2.0) * vac_rms
        vo_avg = (vm - diode_drop) / pi
        io_avg = vo_avg / load_r
        c_required = io_avg / (2.0 * freq * ripple_fraction * vo_avg)
        piv_required = vm

        primary = {
            "vo_avg": vo_avg,
            "io_avg": io_avg,
            "required_capacitance": c_required,
            "piv_required": piv_required,
        }
        assumptions = {"model": "half_wave_rectifier", "ripple_fraction": str(ripple_fraction)}
        return PreDesignResult(primary_values=primary, operating_mode="ccm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        diode_drop = get_optional(spec, "diode_drop", 0.7)
        io_avg = predesign.primary_values["io_avg"]
        conduction_loss = diode_drop * io_avg
        return LossReport(totals={"diode_conduction_w": conduction_loss}, per_element={"diode": conduction_loss})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Output average voltage {predesign.primary_values['vo_avg']:.2f} V with load current "
            f"{predesign.primary_values['io_avg']:.2f} A. Select diode with PIV >= "
            f"{predesign.primary_values['piv_required']:.2f} V and conduction loss {losses.totals['diode_conduction_w']:.2f} W."
        )
        next_steps = ["Validate diode thermal management", "Tune filter capacitance for desired ripple"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


class FullBridgeRectifierDesigner(ConverterDesigner):
    topology_id = TopologyId.AC_DC_RECTIFIER_FULL

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "vac_rms", "freq_ac", "load_resistance")
        for key in ("vac_rms", "freq_ac", "load_resistance"):
            if key not in spec.operating_conditions:
                continue
            if spec.operating_conditions[key] <= 0:
                issues.append(_positive_issue(spec, key))
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vac_rms = require(spec, "vac_rms")
        freq = require(spec, "freq_ac")
        load_r = require(spec, "load_resistance")
        diode_drop = get_optional(spec, "diode_drop", 0.7)
        ripple_pct = spec.constraints.get("voltage_ripple_pct", 5.0)
        ripple_fraction = percentage_to_fraction(ripple_pct)

        vm = sqrt(2.0) * vac_rms
        vo_avg = (2.0 * (vm - diode_drop)) / pi
        io_avg = vo_avg / load_r
        c_required = io_avg / (2.0 * freq * ripple_fraction * vo_avg)
        piv_required = 2.0 * vm

        primary = {
            "vo_avg": vo_avg,
            "io_avg": io_avg,
            "required_capacitance": c_required,
            "piv_required": piv_required,
        }
        return PreDesignResult(primary_values=primary, operating_mode="ccm")

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        diode_drop = get_optional(spec, "diode_drop", 0.7)
        io_avg = predesign.primary_values["io_avg"]
        conduction_loss = 2.0 * diode_drop * io_avg
        totals = {"bridge_diode_w": conduction_loss}
        return LossReport(totals=totals, per_element={"bridge": conduction_loss})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Full bridge average output {predesign.primary_values['vo_avg']:.2f} V, load current "
            f"{predesign.primary_values['io_avg']:.2f} A. Require diode PIV >= "
            f"{predesign.primary_values['piv_required']:.2f} V." 
        )
        next_steps = ["Verify thermal design for bridge", "Confirm ripple tolerance"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


class ThreePhaseRectifierDesigner(ConverterDesigner):
    topology_id = TopologyId.AC_DC_RECTIFIER_THREE_PHASE

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "vll_rms", "freq_ac", "load_resistance")
        for key in ("vll_rms", "freq_ac", "load_resistance"):
            if key not in spec.operating_conditions:
                continue
            if spec.operating_conditions[key] <= 0:
                issues.append(_positive_issue(spec, key))
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vll_rms = require(spec, "vll_rms")
        freq = require(spec, "freq_ac")
        load_r = require(spec, "load_resistance")
        diode_drop = get_optional(spec, "diode_drop", 1.0)
        ripple_pct = spec.constraints.get("voltage_ripple_pct", 3.0)
        ripple_fraction = percentage_to_fraction(ripple_pct)

        vo_avg = 1.35 * vll_rms - 2.0 * diode_drop
        io_avg = vo_avg / load_r
        c_required = io_avg / (6.0 * freq * ripple_fraction * vo_avg)
        piv_required = 1.155 * sqrt(2.0) * vll_rms

        primary = {
            "vo_avg": vo_avg,
            "io_avg": io_avg,
            "required_capacitance": c_required,
            "piv_required": piv_required,
        }
        return PreDesignResult(primary_values=primary, operating_mode="ccm")

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        diode_drop = get_optional(spec, "diode_drop", 1.0)
        io_avg = predesign.primary_values["io_avg"]
        conduction_loss = 2.0 * diode_drop * io_avg
        return LossReport(totals={"diode_conduction_w": conduction_loss}, per_element={"leg": conduction_loss})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Three-phase rectifier delivering {predesign.primary_values['vo_avg']:.2f} V average with "
            f"{predesign.primary_values['io_avg']:.2f} A. Select diodes with PIV >= "
            f"{predesign.primary_values['piv_required']:.2f} V."
        )
        return DesignRecommendation(summary=summary, next_steps=["Check phase balance", "Dimension input inductors if needed"])


class TriacRegulatorDesigner(ConverterDesigner):
    topology_id = TopologyId.AC_AC_TRIAC

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "vac_rms", "freq_ac", "load_resistance", "alpha_deg")
        for key in ("vac_rms", "freq_ac", "load_resistance"):
            if key not in spec.operating_conditions:
                continue
            if spec.operating_conditions[key] <= 0:
                issues.append(_positive_issue(spec, key))
        if "alpha_deg" in spec.operating_conditions:
            alpha = spec.operating_conditions["alpha_deg"]
            if not 0.0 <= alpha <= 180.0:
                issues.append(
                    ValidationIssue(
                        code="alpha_range",
                        message="Trigger angle alpha must be between 0 and 180 degrees",
                        severity=ValidationSeverity.ERROR,
                    )
                )
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vac_rms = require(spec, "vac_rms")
        load_r = require(spec, "load_resistance")
        alpha = require(spec, "alpha_deg", allow_zero=True)

        vac_peak = sqrt(2.0) * vac_rms
        alpha_rad = alpha * pi / 180.0
        term = (pi - alpha_rad + (sin_deg(2 * alpha) / 2.0)) / (2.0 * pi)
        vo_rms = vac_peak * sqrt(term)
        io_rms = vo_rms / load_r
        fundamental = vac_peak * (sqrt(2.0) / pi) * (1 - alpha / 180.0)

        primary = {
            "vo_rms": vo_rms,
            "io_rms": io_rms,
            "fundamental_component": fundamental,
        }
        return PreDesignResult(primary_values=primary, operating_mode="phase_control")

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        triac_drop = get_optional(spec, "triac_drop", 1.2)
        io_rms = predesign.primary_values["io_rms"]
        conduction = triac_drop * io_rms
        return LossReport(totals={"triac_conduction_w": conduction}, per_element={"triac": conduction})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"TRIAC RMS output {predesign.primary_values['vo_rms']:.2f} V at {predesign.primary_values['io_rms']:.2f} A."
            " Ensure holding current and dv/dt limits are satisfied."
        )
        next_steps = ["Validate snubber network for inductive loads", "Check heat sinking requirements"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


class BuckConverterDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_DC_BUCK

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        required = (
            "vin",
            "vo_target",
            "fsw",
            "io_max",
            "delta_il_pct",
            "delta_vo_pct",
        )
        issues = _missing_issues(spec, *required)
        for key in required:
            if key not in spec.operating_conditions:
                continue
            if spec.operating_conditions[key] <= 0:
                issues.append(_positive_issue(spec, key))
        if "vin" in spec.operating_conditions and "vo_target" in spec.operating_conditions:
            if spec.operating_conditions["vo_target"] >= spec.operating_conditions["vin"]:
                issues.append(
                    ValidationIssue(
                        code="buck_vo_less_than_vin",
                        message="For buck converters Vout must be lower than Vin",
                        severity=ValidationSeverity.ERROR,
                    )
                )
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vin = require(spec, "vin")
        vo = require(spec, "vo_target")
        fsw = require(spec, "fsw")
        io_max = require(spec, "io_max")
        delta_il = percentage_to_fraction(require(spec, "delta_il_pct")) * io_max
        delta_vo = percentage_to_fraction(require(spec, "delta_vo_pct")) * vo
        r_l = get_optional(spec, "r_l", 0.05)

        duty = vo / vin
        inductance = (vin - vo) * duty / (delta_il * fsw)
        capacitance = delta_il / (8.0 * delta_vo * fsw)
        i_l_rms = triangular_rms(io_max, delta_il)
        i_sw_rms = sqrt(duty) * io_max

        primary = {
            "duty": duty,
            "inductance": inductance,
            "capacitance": capacitance,
            "i_l_rms": i_l_rms,
            "i_sw_rms": i_sw_rms,
        }
        assumptions = {"mode": "ccm", "delta_il": str(delta_il), "delta_vo": str(delta_vo)}
        return PreDesignResult(primary_values=primary, operating_mode="ccm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_l = get_optional(spec, "r_l", 0.05)
        r_on = get_optional(spec, "r_on", 0.03)
        esr_c = get_optional(spec, "esr_c", 0.02)
        v_d = get_optional(spec, "v_d", 0.7)
        io_max = require(spec, "io_max")
        duty = predesign.primary_values["duty"]
        i_l_rms = predesign.primary_values["i_l_rms"]
        i_sw_rms = predesign.primary_values["i_sw_rms"]
        delta_il = float(predesign.assumptions["delta_il"])

        p_inductor = i_l_rms**2 * r_l
        p_switch = i_sw_rms**2 * r_on
        i_d_avg = (1.0 - duty) * io_max
        p_diode = i_d_avg * v_d
        i_c_rms = capacitor_ripple_current(delta_il)
        p_cap = i_c_rms**2 * esr_c
        total = p_inductor + p_switch + p_diode + p_cap
        return LossReport(
            totals={
                "inductor_w": p_inductor,
                "switch_w": p_switch,
                "diode_w": p_diode,
                "capacitor_w": p_cap,
                "total_loss_w": total,
            },
            per_element={"inductor": p_inductor, "switch": p_switch, "diode": p_diode, "capacitor": p_cap},
        )

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        output_power = require(spec, "vo_target") * require(spec, "io_max")
        total_loss = losses.totals["total_loss_w"]
        efficiency = output_power / (output_power + total_loss)
        summary = (
            f"Buck converter duty {predesign.primary_values['duty']:.3f}, L={predesign.primary_values['inductance']:.6f} H, "
            f"C={predesign.primary_values['capacitance']:.6f} F. Estimated efficiency {efficiency*100:.1f}%"
        )
        next_steps = ["Select MOSFET/diode meeting current stress", "Verify thermal design"]
        metadata = {"efficiency": f"{efficiency:.4f}"}
        return DesignRecommendation(summary=summary, next_steps=next_steps, metadata=metadata)


class BoostConverterDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_DC_BOOST

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        required = (
            "vin",
            "vo_target",
            "fsw",
            "io_max",
            "delta_il_pct",
            "delta_vo_pct",
        )
        issues = _missing_issues(spec, *required)
        for key in required:
            if key not in spec.operating_conditions:
                continue
            if spec.operating_conditions[key] <= 0:
                issues.append(_positive_issue(spec, key))
        if "vin" in spec.operating_conditions and "vo_target" in spec.operating_conditions:
            if spec.operating_conditions["vo_target"] <= spec.operating_conditions["vin"]:
                issues.append(
                    ValidationIssue(
                        code="boost_vo_greater_vin",
                        message="For boost converters Vout must exceed Vin",
                        severity=ValidationSeverity.ERROR,
                    )
                )
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vin = require(spec, "vin")
        vo = require(spec, "vo_target")
        fsw = require(spec, "fsw")
        io_max = require(spec, "io_max")
        delta_il = percentage_to_fraction(require(spec, "delta_il_pct")) * io_max / (1 - vin / vo)
        delta_vo = percentage_to_fraction(require(spec, "delta_vo_pct")) * vo
        duty = 1.0 - vin / vo
        inductance = vin * duty / (delta_il * fsw)
        capacitance = io_max * duty / (delta_vo * fsw)
        il_avg = io_max / (1.0 - duty)
        i_l_rms = triangular_rms(il_avg, delta_il)
        i_sw_rms = i_l_rms * sqrt(duty)

        primary = {
            "duty": duty,
            "inductance": inductance,
            "capacitance": capacitance,
            "i_l_rms": i_l_rms,
            "i_sw_rms": i_sw_rms,
            "il_avg": il_avg,
        }
        assumptions = {"delta_il": str(delta_il), "delta_vo": str(delta_vo)}
        return PreDesignResult(primary_values=primary, operating_mode="ccm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_l = get_optional(spec, "r_l", 0.05)
        r_on = get_optional(spec, "r_on", 0.04)
        esr_c = get_optional(spec, "esr_c", 0.03)
        v_d = get_optional(spec, "v_d", 0.7)
        duty = predesign.primary_values["duty"]
        il_avg = predesign.primary_values["il_avg"]
        i_l_rms = predesign.primary_values["i_l_rms"]
        i_sw_rms = predesign.primary_values["i_sw_rms"]
        io_max = require(spec, "io_max")
        delta_il = float(predesign.assumptions["delta_il"])

        p_inductor = i_l_rms**2 * r_l
        p_switch = i_sw_rms**2 * r_on
        p_diode = io_max * v_d
        i_c_rms = capacitor_ripple_current(delta_il)
        p_cap = i_c_rms**2 * esr_c
        total = p_inductor + p_switch + p_diode + p_cap
        totals = {
            "inductor_w": p_inductor,
            "switch_w": p_switch,
            "diode_w": p_diode,
            "capacitor_w": p_cap,
            "total_loss_w": total,
        }
        return LossReport(totals=totals, per_element={"inductor": p_inductor, "switch": p_switch, "diode": p_diode, "capacitor": p_cap})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        vo = require(spec, "vo_target")
        io = require(spec, "io_max")
        output_power = vo * io
        total_loss = losses.totals["total_loss_w"]
        efficiency = output_power / (output_power + total_loss)
        summary = (
            f"Boost converter duty {predesign.primary_values['duty']:.3f}, L={predesign.primary_values['inductance']:.6f} H, "
            f"C={predesign.primary_values['capacitance']:.6f} F. Estimated efficiency {efficiency*100:.1f}%"
        )
        return DesignRecommendation(summary=summary, next_steps=["Confirm diode reverse stress", "Validate EMI filter"], metadata={"efficiency": f"{efficiency:.4f}"})


class BuckBoostConverterDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_DC_BUCK_BOOST

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        required = (
            "vin",
            "vo_target",
            "fsw",
            "io_max",
            "delta_il_pct",
            "delta_vo_pct",
        )
        issues = _missing_issues(spec, *required)
        for key in required:
            if key not in spec.operating_conditions:
                continue
            if spec.operating_conditions[key] <= 0 and key != "vo_target":
                issues.append(_positive_issue(spec, key))
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vin = require(spec, "vin")
        vo = abs(require(spec, "vo_target", allow_negative=True))
        fsw = require(spec, "fsw")
        io = require(spec, "io_max")
        duty = vo / (vo + vin)
        delta_il = percentage_to_fraction(require(spec, "delta_il_pct")) * io * (1.0 - duty) / duty
        delta_vo = percentage_to_fraction(require(spec, "delta_vo_pct")) * vo
        inductance = vin * duty / (delta_il * fsw)
        capacitance = io * duty / (delta_vo * fsw)
        il_avg = io * (1.0 - duty) / duty
        i_l_rms = triangular_rms(il_avg, delta_il)

        primary = {
            "duty": duty,
            "inductance": inductance,
            "capacitance": capacitance,
            "il_avg": il_avg,
            "i_l_rms": i_l_rms,
        }
        assumptions = {"delta_il": str(delta_il), "delta_vo": str(delta_vo)}
        return PreDesignResult(primary_values=primary, operating_mode="ccm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_l = get_optional(spec, "r_l", 0.08)
        r_on = get_optional(spec, "r_on", 0.05)
        esr_c = get_optional(spec, "esr_c", 0.03)
        v_d = get_optional(spec, "v_d", 0.7)
        duty = predesign.primary_values["duty"]
        il_avg = predesign.primary_values["il_avg"]
        i_l_rms = predesign.primary_values["i_l_rms"]
        delta_il = float(predesign.assumptions["delta_il"])
        io = require(spec, "io_max")

        p_inductor = i_l_rms**2 * r_l
        p_switch = (il_avg * sqrt(duty))**2 * r_on
        p_diode = il_avg * (1.0 - duty) * v_d
        i_c_rms = capacitor_ripple_current(delta_il)
        p_cap = i_c_rms**2 * esr_c
        total = p_inductor + p_switch + p_diode + p_cap
        totals = {
            "inductor_w": p_inductor,
            "switch_w": p_switch,
            "diode_w": p_diode,
            "capacitor_w": p_cap,
            "total_loss_w": total,
        }
        return LossReport(totals=totals, per_element={"inductor": p_inductor, "switch": p_switch, "diode": p_diode, "capacitor": p_cap})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        vo = abs(require(spec, "vo_target", allow_negative=True))
        io = require(spec, "io_max")
        output_power = vo * io
        efficiency = output_power / (output_power + losses.totals["total_loss_w"])
        summary = (
            f"Buck-boost duty {predesign.primary_values['duty']:.3f} (negative output). L={predesign.primary_values['inductance']:.6f} H, "
            f"C={predesign.primary_values['capacitance']:.6f} F. Eff={efficiency*100:.1f}%"
        )
        return DesignRecommendation(summary=summary, next_steps=["Check polarity inversion in load", "Validate snubber network"], metadata={"efficiency": f"{efficiency:.4f}"})


class CukConverterDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_DC_CUK

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        required = (
            "vin",
            "vo_target",
            "fsw",
            "io_max",
            "delta_il1_pct",
            "delta_il2_pct",
            "delta_vo_pct",
        )
        issues = _missing_issues(spec, *required)
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vin = require(spec, "vin")
        vo = abs(require(spec, "vo_target", allow_negative=True))
        fsw = require(spec, "fsw")
        io = require(spec, "io_max")
        duty = vo / (vo + vin)
        delta_il1 = percentage_to_fraction(require(spec, "delta_il1_pct")) * io
        delta_il2 = percentage_to_fraction(require(spec, "delta_il2_pct")) * io
        delta_vo = percentage_to_fraction(require(spec, "delta_vo_pct")) * vo

        l1 = vin * duty / (delta_il1 * fsw)
        l2 = vo * (1.0 - duty) / (delta_il2 * fsw)
        c1 = io * duty / (delta_il1 * fsw)
        c2 = io * duty / (delta_vo * fsw)

        primary = {
            "duty": duty,
            "l1": l1,
            "l2": l2,
            "c1": c1,
            "c2": c2,
        }
        assumptions = {"delta_il1": str(delta_il1), "delta_il2": str(delta_il2), "delta_vo": str(delta_vo)}
        return PreDesignResult(primary_values=primary, operating_mode="ccm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_l1 = get_optional(spec, "r_l1", 0.05)
        r_l2 = get_optional(spec, "r_l2", 0.05)
        esr_c1 = get_optional(spec, "esr_c1", 0.02)
        esr_c2 = get_optional(spec, "esr_c2", 0.02)
        r_on = get_optional(spec, "r_on", 0.05)
        v_d = get_optional(spec, "v_d", 0.7)
        io = require(spec, "io_max")
        duty = predesign.primary_values["duty"]

        il1_rms = io * sqrt(duty)
        il2_rms = io * sqrt(1.0 - duty)
        p_l1 = il1_rms**2 * r_l1
        p_l2 = il2_rms**2 * r_l2
        p_cap1 = (io**2) * esr_c1
        p_cap2 = (io**2) * esr_c2
        p_switch = (io**2) * r_on
        p_diode = io * v_d
        total = p_l1 + p_l2 + p_cap1 + p_cap2 + p_switch + p_diode
        totals = {
            "l1_w": p_l1,
            "l2_w": p_l2,
            "c1_w": p_cap1,
            "c2_w": p_cap2,
            "switch_w": p_switch,
            "diode_w": p_diode,
            "total_loss_w": total,
        }
        return LossReport(totals=totals, per_element={"l1": p_l1, "l2": p_l2, "c1": p_cap1, "c2": p_cap2, "switch": p_switch, "diode": p_diode})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        vo = abs(require(spec, "vo_target", allow_negative=True))
        io = require(spec, "io_max")
        output_power = vo * io
        efficiency = output_power / (output_power + losses.totals["total_loss_w"])
        summary = (
            f"Ćuk converter duty {predesign.primary_values['duty']:.3f} with L1={predesign.primary_values['l1']:.6f} H, "
            f"L2={predesign.primary_values['l2']:.6f} H." 
        )
        next_steps = ["Use low-ESR coupling capacitor", "Validate ripple on C1"]
        return DesignRecommendation(summary=summary, next_steps=next_steps, metadata={"efficiency": f"{efficiency:.4f}"})


class FlybackConverterDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_DC_FLYBACK

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        required = (
            "vin_min",
            "vin_max",
            "vo_target",
            "fsw",
            "pout",
            "duty_max",
            "turns_ratio",
        )
        issues = _missing_issues(spec, *required)
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vin_min = require(spec, "vin_min")
        vin_max = require(spec, "vin_max")
        vo = require(spec, "vo_target")
        fsw = require(spec, "fsw")
        pout = require(spec, "pout")
        duty_max = require(spec, "duty_max")
        turns_ratio = require(spec, "turns_ratio")

        duty = min(duty_max, vo * turns_ratio / (vo * turns_ratio + vin_min))
        i_out = pout / vo
        i_pk = 2.0 * pout / (vin_min * duty * fsw)
        l_mag = 2.0 * pout / (i_pk**2 * fsw)
        c_out = i_out * duty / (percentage_to_fraction(spec.operating_conditions.get("delta_vo_pct", 2.0)) * vo * fsw)
        v_sw_max = vin_max + turns_ratio * vo

        primary = {
            "duty": duty,
            "lm": l_mag,
            "i_pk": i_pk,
            "c_out": c_out,
            "v_sw_max": v_sw_max,
        }
        assumptions = {"turns_ratio": str(turns_ratio)}
        return PreDesignResult(primary_values=primary, operating_mode="dccm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_on = get_optional(spec, "r_on", 0.05)
        v_d = get_optional(spec, "v_d", 0.7)
        r_copper = get_optional(spec, "r_copper", 0.1)
        pout = require(spec, "pout")
        vo = require(spec, "vo_target")
        io = pout / vo
        i_pk = predesign.primary_values["i_pk"]
        duty = predesign.primary_values["duty"]

        i_rms_primary = i_pk * sqrt(duty / 3.0)
        p_switch = i_rms_primary**2 * r_on
        p_copper = i_rms_primary**2 * r_copper
        p_diode = io * v_d
        total = p_switch + p_copper + p_diode
        totals = {
            "switch_w": p_switch,
            "copper_w": p_copper,
            "diode_w": p_diode,
            "total_loss_w": total,
        }
        return LossReport(totals=totals, per_element={"switch": p_switch, "winding": p_copper, "diode": p_diode})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Flyback with turns ratio {predesign.assumptions['turns_ratio']} and peak current {predesign.primary_values['i_pk']:.2f} A. "
            f"Ensure switch can withstand {predesign.primary_values['v_sw_max']:.1f} V."
        )
        next_steps = ["Design snubber to clamp leakage spikes", "Validate core selection vs flux density"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


class HalfBridgeInverterDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_AC_HALF_BRIDGE

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "vdc", "vo_rms", "fo", "fsw", "po", "thd_target")
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vdc = require(spec, "vdc")
        vo_rms = require(spec, "vo_rms")
        fo = require(spec, "fo")
        fsw = require(spec, "fsw")
        po = require(spec, "po")
        thd_target = require(spec, "thd_target")
        ma = min((2.0 * sqrt(2.0) * vo_rms) / vdc, 1.0)
        vo_peak = ma * vdc / 2.0
        lf = vdc / (8.0 * pi * fo * po**0.5)
        cf = 1.0 / ((2.0 * pi * fo) ** 2 * lf)

        primary = {
            "modulation_index": ma,
            "vo_peak": vo_peak,
            "lf": lf,
            "cf": cf,
        }
        assumptions = {"thd_target": str(thd_target), "fsw": str(fsw)}
        return PreDesignResult(primary_values=primary, operating_mode="spwm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_on = get_optional(spec, "r_on", 0.03)
        v_d = get_optional(spec, "v_d", 1.0)
        vo_rms = require(spec, "vo_rms")
        load_current = require(spec, "po") / vo_rms
        conduction = load_current**2 * r_on
        diode = load_current * v_d
        total = conduction + diode
        return LossReport(totals={"conduction_w": conduction, "diode_w": diode, "total_loss_w": total})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Half-bridge inverter M_a={predesign.primary_values['modulation_index']:.3f}, Lf={predesign.primary_values['lf']:.6f} H, "
            f"Cf={predesign.primary_values['cf']:.6f} F."
        )
        next_steps = ["Balance DC bus capacitors", "Validate gate driver deadtime"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


class FullBridgeSinglePhaseDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_AC_FULL_BRIDGE_SINGLE

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "vdc", "vo_rms", "fo", "fsw", "po")
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vdc = require(spec, "vdc")
        vo_rms = require(spec, "vo_rms")
        fo = require(spec, "fo")
        fsw = require(spec, "fsw")
        po = require(spec, "po")
        ma = min(2.0 * vo_rms / (vdc / sqrt(2.0)), 1.0)
        vo_peak = ma * vdc / 2.0
        lf = vo_peak / (4.0 * pi * fo * po**0.5)
        cf = 1.0 / ((2.0 * pi * fo) ** 2 * lf)

        primary = {
            "modulation_index": ma,
            "vo_peak": vo_peak,
            "lf": lf,
            "cf": cf,
        }
        assumptions = {"fsw": str(fsw)}
        return PreDesignResult(primary_values=primary, operating_mode="spwm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_on = get_optional(spec, "r_on", 0.03)
        v_d = get_optional(spec, "v_d", 1.0)
        vo_rms = require(spec, "vo_rms")
        po = require(spec, "po")
        i_rms = po / vo_rms
        conduction = i_rms**2 * r_on
        diode = i_rms * v_d
        total = conduction + diode
        return LossReport(totals={"switch_conduction_w": conduction, "diode_w": diode, "total_loss_w": total})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Full-bridge inverter M_a={predesign.primary_values['modulation_index']:.3f}, Lf={predesign.primary_values['lf']:.6f} H, "
            f"Cf={predesign.primary_values['cf']:.6f} F."
        )
        next_steps = ["Ensure deadtime avoids shoot-through", "Consider SPWM vs SVPWM"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


class FullBridgeThreePhaseDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_AC_FULL_BRIDGE_THREE

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "vdc", "vll_rms", "fo", "fsw", "po")
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        vdc = require(spec, "vdc")
        vll_rms = require(spec, "vll_rms")
        fo = require(spec, "fo")
        fsw = require(spec, "fsw")
        po = require(spec, "po")
        vf_phase = vll_rms / sqrt(3.0)
        ma = min(2.0 * vf_phase / (vdc / 2.0), 1.0)
        vo_phase_peak = ma * vdc / 2.0
        lf = vdc / (6.0 * pi * fo * po**0.5)
        cf = 1.0 / ((2.0 * pi * fo) ** 2 * lf)

        primary = {
            "modulation_index": ma,
            "vo_phase_peak": vo_phase_peak,
            "lf": lf,
            "cf": cf,
        }
        assumptions = {"fsw": str(fsw)}
        return PreDesignResult(primary_values=primary, operating_mode="spwm", assumptions=assumptions)

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        r_on = get_optional(spec, "r_on", 0.03)
        v_d = get_optional(spec, "v_d", 1.0)
        vll_rms = require(spec, "vll_rms")
        po = require(spec, "po")
        i_line = po / (sqrt(3.0) * vll_rms)
        conduction = 3.0 * (i_line**2 * r_on)
        diode = 3.0 * i_line * v_d
        total = conduction + diode
        totals = {"switch_conduction_w": conduction, "diode_w": diode, "total_loss_w": total}
        return LossReport(totals=totals)

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Three-phase inverter M_a={predesign.primary_values['modulation_index']:.3f}, Lf={predesign.primary_values['lf']:.6f} H."
        )
        next_steps = ["Verify phase current balance", "Plan for SVPWM if higher DC bus utilization is desired"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


class ModulationDesigner(ConverterDesigner):
    topology_id = TopologyId.DC_AC_MODULATION

    def validate_input(self, spec: ConverterSpec) -> List[ValidationIssue]:
        issues = _missing_issues(spec, "carrier_freq", "fundamental_freq", "modulation_index")
        return issues

    def pre_design(self, spec: ConverterSpec) -> PreDesignResult:
        fc = require(spec, "carrier_freq")
        fo = require(spec, "fundamental_freq")
        ma = min(max(require(spec, "modulation_index", allow_zero=True), 0.0), 1.15)
        mf = fc / fo
        vo_normalized = ma

        primary = {
            "ma": ma,
            "mf": mf,
            "normalized_voltage": vo_normalized,
        }
        return PreDesignResult(primary_values=primary, operating_mode="modulation")

    def estimate_losses(self, predesign: PreDesignResult, spec: ConverterSpec) -> LossReport:
        switching_freq = require(spec, "carrier_freq")
        base_loss = switching_freq * 1e-6
        return LossReport(totals={"switching_loss_w": base_loss})

    def compose_recommendation(
        self,
        predesign: PreDesignResult,
        losses: LossReport,
        spec: ConverterSpec,
    ) -> DesignRecommendation:
        summary = (
            f"Modulation index {predesign.primary_values['ma']:.3f} with frequency ratio m_f={predesign.primary_values['mf']:.1f}."
        )
        next_steps = ["Maintain carrier ratio above 15", "Consider SVPWM for higher utilization"]
        return DesignRecommendation(summary=summary, next_steps=next_steps)


def register_default_designers(factory: ConverterFactory) -> None:
    """Register all default designer implementations in the provided factory."""

    factory.register(TopologyId.AC_DC_RECTIFIER_SINGLE, HalfWaveRectifierDesigner)
    factory.register(TopologyId.AC_DC_RECTIFIER_FULL, FullBridgeRectifierDesigner)
    factory.register(TopologyId.AC_DC_RECTIFIER_THREE_PHASE, ThreePhaseRectifierDesigner)
    factory.register(TopologyId.AC_AC_TRIAC, TriacRegulatorDesigner)
    factory.register(TopologyId.DC_DC_BUCK, BuckConverterDesigner)
    factory.register(TopologyId.DC_DC_BOOST, BoostConverterDesigner)
    factory.register(TopologyId.DC_DC_BUCK_BOOST, BuckBoostConverterDesigner)
    factory.register(TopologyId.DC_DC_CUK, CukConverterDesigner)
    factory.register(TopologyId.DC_DC_FLYBACK, FlybackConverterDesigner)
    factory.register(TopologyId.DC_AC_HALF_BRIDGE, HalfBridgeInverterDesigner)
    factory.register(TopologyId.DC_AC_FULL_BRIDGE_SINGLE, FullBridgeSinglePhaseDesigner)
    factory.register(TopologyId.DC_AC_FULL_BRIDGE_THREE, FullBridgeThreePhaseDesigner)
    factory.register(TopologyId.DC_AC_MODULATION, ModulationDesigner)
