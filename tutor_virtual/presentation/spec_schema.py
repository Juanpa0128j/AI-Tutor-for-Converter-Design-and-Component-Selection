"""Form schema definitions for the presentation wizard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

from tutor_virtual.domain.converters.base import TopologyId


@dataclass(slots=True)
class FieldDefinition:
    """Represents a single input field exposed to the user."""

    key: str
    label: str
    placeholder: str
    unit: str  # Physical unit (V, A, Hz, W, %, etc.)
    default: float | str | None = None
    is_constraint: bool = False
    allow_negative: bool = False
    allow_zero: bool = False


@dataclass(slots=True)
class TopologyForm:
    """Describes how to capture input for a given topology."""

    topology_id: TopologyId
    title: str
    description: str
    fields: Sequence[FieldDefinition]
    constraint_fields: Sequence[FieldDefinition] = ()


def _fields(*fields: FieldDefinition) -> Sequence[FieldDefinition]:
    return list(fields)


FORMS: Mapping[TopologyId, TopologyForm] = {
    TopologyId.DC_DC_BUCK: TopologyForm(
        topology_id=TopologyId.DC_DC_BUCK,
        title="topo_buck_title",
        description="topo_buck_desc",
        fields=_fields(
            FieldDefinition("vin", "lbl_vin", "24", unit="V"),
            FieldDefinition("vo_target", "lbl_vo_target", "12", unit="V"),
            FieldDefinition("fsw", "lbl_fsw", "50000", unit="Hz"),
            FieldDefinition("io_max", "lbl_io_max", "5", unit="A"),
            FieldDefinition("delta_il_pct", "lbl_delta_il", "20", unit="%"),
            FieldDefinition("delta_vo_pct", "lbl_delta_vo", "2", unit="%"),
        ),
        constraint_fields=_fields(
            FieldDefinition("voltage_ripple_pct", "lbl_ripple_voltage", "2", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.DC_DC_BOOST: TopologyForm(
        topology_id=TopologyId.DC_DC_BOOST,
        title="topo_boost_title",
        description="topo_boost_desc",
        fields=_fields(
            FieldDefinition("vin", "lbl_vin", "12", unit="V"),
            FieldDefinition("vo_target", "lbl_vo_target", "24", unit="V"),
            FieldDefinition("fsw", "lbl_fsw", "50000", unit="Hz"),
            FieldDefinition("io_max", "lbl_io_max", "3", unit="A"),
            FieldDefinition("delta_il_pct", "lbl_delta_il", "30", unit="%"),
            FieldDefinition("delta_vo_pct", "lbl_delta_vo", "2", unit="%"),
        ),
    ),
    TopologyId.DC_DC_BUCK_BOOST: TopologyForm(
        topology_id=TopologyId.DC_DC_BUCK_BOOST,
        title="topo_buck_boost_title",
        description="topo_buck_boost_desc",
        fields=_fields(
            FieldDefinition("vin", "lbl_vin", "12", unit="V"),
            FieldDefinition("vo_target", "lbl_vo_target_neg", "-12", unit="V", allow_negative=True),
            FieldDefinition("fsw", "lbl_fsw", "50000", unit="Hz"),
            FieldDefinition("io_max", "lbl_io_max", "2", unit="A"),
            FieldDefinition("delta_il_pct", "lbl_delta_il", "30", unit="%"),
            FieldDefinition("delta_vo_pct", "lbl_delta_vo", "2", unit="%"),
        ),
    ),
    TopologyId.DC_DC_CUK: TopologyForm(
        topology_id=TopologyId.DC_DC_CUK,
        title="topo_cuk_title",
        description="topo_cuk_desc",
        fields=_fields(
            FieldDefinition("vin", "lbl_vin", "12", unit="V"),
            FieldDefinition("vo_target", "lbl_vo_target_any", "-24", unit="V", allow_negative=True),
            FieldDefinition("fsw", "lbl_fsw", "50000", unit="Hz"),
            FieldDefinition("io_max", "lbl_io_max", "2", unit="A"),
            FieldDefinition("delta_il1_pct", "lbl_delta_il1", "20", unit="%"),
            FieldDefinition("delta_il2_pct", "lbl_delta_il2", "20", unit="%"),
            FieldDefinition("delta_vo_pct", "lbl_delta_vo", "2", unit="%"),
        ),
    ),
    TopologyId.DC_DC_FLYBACK: TopologyForm(
        topology_id=TopologyId.DC_DC_FLYBACK,
        title="topo_flyback_title",
        description="topo_flyback_desc",
        fields=_fields(
            FieldDefinition("vin_min", "lbl_vin_min", "18", unit="V"),
            FieldDefinition("vin_max", "lbl_vin_max", "36", unit="V"),
            FieldDefinition("vo_target", "lbl_vo_target", "12", unit="V"),
            FieldDefinition("fsw", "lbl_fsw", "100000", unit="Hz"),
            FieldDefinition("pout", "lbl_pout", "30", unit="W"),
            FieldDefinition("duty_max", "lbl_duty_max", "0.45", unit="", allow_zero=True),
            FieldDefinition("turns_ratio", "lbl_turns_ratio", "1.5", unit=""),
        ),
        constraint_fields=_fields(
            FieldDefinition("delta_vo_pct", "lbl_ripple_vo", "2", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.AC_DC_RECTIFIER_SINGLE: TopologyForm(
        topology_id=TopologyId.AC_DC_RECTIFIER_SINGLE,
        title="topo_rect_single_title",
        description="topo_rect_single_desc",
        fields=_fields(
            FieldDefinition("vac_rms", "lbl_vac_rms", "120", unit="V"),
            FieldDefinition("freq_ac", "lbl_freq_ac", "60", unit="Hz"),
            FieldDefinition("load_resistance", "lbl_load_resistance", "100", unit="Ω"),
        ),
        constraint_fields=_fields(
            FieldDefinition("voltage_ripple_pct", "lbl_ripple_vo", "5", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.AC_DC_RECTIFIER_FULL: TopologyForm(
        topology_id=TopologyId.AC_DC_RECTIFIER_FULL,
        title="topo_rect_full_title",
        description="topo_rect_full_desc",
        fields=_fields(
            FieldDefinition("vac_rms", "lbl_vac_rms", "120", unit="V"),
            FieldDefinition("freq_ac", "lbl_freq_ac", "60", unit="Hz"),
            FieldDefinition("load_resistance", "lbl_load_resistance", "50", unit="Ω"),
        ),
        constraint_fields=_fields(
            FieldDefinition("voltage_ripple_pct", "lbl_ripple_vo", "5", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.AC_AC_TRIAC: TopologyForm(
        topology_id=TopologyId.AC_AC_TRIAC,
        title="topo_triac_title",
        description="topo_triac_desc",
        fields=_fields(
            FieldDefinition("vac_rms", "lbl_vac_rms", "120", unit="V"),
            FieldDefinition("freq_ac", "lbl_freq_ac", "60", unit="Hz"),
            FieldDefinition("load_resistance", "lbl_load_resistance", "100", unit="Ω"),
            FieldDefinition("alpha_deg", "lbl_alpha_deg", "90", unit="°", allow_zero=True),
        ),
    ),
    TopologyId.DC_AC_HALF_BRIDGE: TopologyForm(
        topology_id=TopologyId.DC_AC_HALF_BRIDGE,
        title="topo_inv_half_title",
        description="topo_inv_half_desc",
        fields=_fields(
            FieldDefinition("vdc", "lbl_vdc", "400", unit="V"),
            FieldDefinition("vo_rms", "lbl_vo_rms", "120", unit="V"),
            FieldDefinition("fo", "lbl_fo", "50", unit="Hz"),
            FieldDefinition("fsw", "lbl_fsw", "10000", unit="Hz"),
            FieldDefinition("po", "lbl_pout", "1000", unit="W"),
            FieldDefinition("thd_target", "lbl_thd_target", "5", unit="%"),
        ),
    ),
    TopologyId.DC_AC_FULL_BRIDGE_SINGLE: TopologyForm(
        topology_id=TopologyId.DC_AC_FULL_BRIDGE_SINGLE,
        title="topo_inv_full_single_title",
        description="topo_inv_full_single_desc",
        fields=_fields(
            FieldDefinition("vdc", "lbl_vdc", "400", unit="V"),
            FieldDefinition("vo_rms", "lbl_vo_rms", "230", unit="V"),
            FieldDefinition("fo", "lbl_fo", "50", unit="Hz"),
            FieldDefinition("fsw", "lbl_fsw", "10000", unit="Hz"),
            FieldDefinition("po", "lbl_pout", "1500", unit="W"),
        ),
    ),
    TopologyId.DC_AC_FULL_BRIDGE_THREE: TopologyForm(
        topology_id=TopologyId.DC_AC_FULL_BRIDGE_THREE,
        title="topo_inv_full_three_title",
        description="topo_inv_full_three_desc",
        fields=_fields(
            FieldDefinition("vdc", "lbl_vdc", "700", unit="V"),
            FieldDefinition("vll_rms", "lbl_vll_rms", "400", unit="V"),
            FieldDefinition("fo", "lbl_fo", "50", unit="Hz"),
            FieldDefinition("fsw", "lbl_fsw", "8000", unit="Hz"),
            FieldDefinition("po", "lbl_pout", "3000", unit="W"),
        ),
    ),
    TopologyId.DC_AC_MODULATION: TopologyForm(
        topology_id=TopologyId.DC_AC_MODULATION,
        title="topo_pwm_title",
        description="topo_pwm_desc",
        fields=_fields(
            FieldDefinition("carrier_freq", "lbl_carrier_freq", "10000", unit="Hz"),
            FieldDefinition("fundamental_freq", "lbl_fund_freq", "50", unit="Hz"),
            FieldDefinition("modulation_index", "lbl_mod_index", "0.8", unit="", allow_zero=True),
        ),
    ),
}


def available_forms(topologies: Iterable[TopologyId]) -> List[TopologyForm]:
    return [FORMS[topology] for topology in topologies if topology in FORMS]
