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
        title="Buck (Reductor)",
        description="Convertidor DC-DC reductor en modo CCM",
        fields=_fields(
            FieldDefinition("vin", "Vin", "24", unit="V"),
            FieldDefinition("vo_target", "Vout deseada", "12", unit="V"),
            FieldDefinition("fsw", "Frecuencia de conmutación", "50000", unit="Hz"),
            FieldDefinition("io_max", "Corriente de salida", "5", unit="A"),
            FieldDefinition("delta_il_pct", "Rizo permitido IL", "20", unit="%"),
            FieldDefinition("delta_vo_pct", "Rizo permitido Vo", "2", unit="%"),
        ),
        constraint_fields=_fields(
            FieldDefinition("voltage_ripple_pct", "Rizo máximo en voltaje", "2", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.DC_DC_BOOST: TopologyForm(
        topology_id=TopologyId.DC_DC_BOOST,
        title="Boost (Elevador)",
        description="Convertidor DC-DC elevador en CCM",
        fields=_fields(
            FieldDefinition("vin", "Vin", "12", unit="V"),
            FieldDefinition("vo_target", "Vout deseada", "24", unit="V"),
            FieldDefinition("fsw", "Frecuencia de conmutación", "50000", unit="Hz"),
            FieldDefinition("io_max", "Corriente de salida", "3", unit="A"),
            FieldDefinition("delta_il_pct", "Rizo permitido IL", "30", unit="%"),
            FieldDefinition("delta_vo_pct", "Rizo permitido Vo", "2", unit="%"),
        ),
    ),
    TopologyId.DC_DC_BUCK_BOOST: TopologyForm(
        topology_id=TopologyId.DC_DC_BUCK_BOOST,
        title="Buck-Boost (Polaridad invertida)",
        description="Convertidor reductor-elevador con salida negativa",
        fields=_fields(
            FieldDefinition("vin", "Vin", "12", unit="V"),
            FieldDefinition("vo_target", "Vout deseada (negativa)", "-12", unit="V", allow_negative=True),
            FieldDefinition("fsw", "Frecuencia de conmutación", "50000", unit="Hz"),
            FieldDefinition("io_max", "Corriente de salida", "2", unit="A"),
            FieldDefinition("delta_il_pct", "Rizo permitido IL", "30", unit="%"),
            FieldDefinition("delta_vo_pct", "Rizo permitido Vo", "2", unit="%"),
        ),
    ),
    TopologyId.DC_DC_CUK: TopologyForm(
        topology_id=TopologyId.DC_DC_CUK,
        title="Ćuk",
        description="Convertidor Ćuk en modo continuo",
        fields=_fields(
            FieldDefinition("vin", "Vin", "12", unit="V"),
            FieldDefinition("vo_target", "Vout (puede ser negativa)", "-24", unit="V", allow_negative=True),
            FieldDefinition("fsw", "Frecuencia de conmutación", "50000", unit="Hz"),
            FieldDefinition("io_max", "Corriente de salida", "2", unit="A"),
            FieldDefinition("delta_il1_pct", "Rizo permitido IL1", "20", unit="%"),
            FieldDefinition("delta_il2_pct", "Rizo permitido IL2", "20", unit="%"),
            FieldDefinition("delta_vo_pct", "Rizo permitido Vo", "2", unit="%"),
        ),
    ),
    TopologyId.DC_DC_FLYBACK: TopologyForm(
        topology_id=TopologyId.DC_DC_FLYBACK,
        title="Flyback",
        description="Convertidor Flyback aislado",
        fields=_fields(
            FieldDefinition("vin_min", "Vin mínima", "18", unit="V"),
            FieldDefinition("vin_max", "Vin máxima", "36", unit="V"),
            FieldDefinition("vo_target", "Vout", "12", unit="V"),
            FieldDefinition("fsw", "Frecuencia de conmutación", "100000", unit="Hz"),
            FieldDefinition("pout", "Potencia de salida", "30", unit="W"),
            FieldDefinition("duty_max", "Duty máximo permitido", "0.45", unit="", allow_zero=True),
            FieldDefinition("turns_ratio", "Relación Np/Ns", "1.5", unit=""),
        ),
        constraint_fields=_fields(
            FieldDefinition("delta_vo_pct", "Rizo máximo Vo", "2", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.AC_DC_RECTIFIER_SINGLE: TopologyForm(
        topology_id=TopologyId.AC_DC_RECTIFIER_SINGLE,
        title="Rectificador monofásico media onda",
        description="Rectificador AC-DC básico",
        fields=_fields(
            FieldDefinition("vac_rms", "Vac RMS", "120", unit="V"),
            FieldDefinition("freq_ac", "Frecuencia red", "60", unit="Hz"),
            FieldDefinition("load_resistance", "Carga R", "100", unit="Ω"),
        ),
        constraint_fields=_fields(
            FieldDefinition("voltage_ripple_pct", "Rizo máximo Vo", "5", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.AC_DC_RECTIFIER_FULL: TopologyForm(
        topology_id=TopologyId.AC_DC_RECTIFIER_FULL,
        title="Rectificador puente monofásico",
        description="Rectificador de onda completa",
        fields=_fields(
            FieldDefinition("vac_rms", "Vac RMS", "120", unit="V"),
            FieldDefinition("freq_ac", "Frecuencia red", "60", unit="Hz"),
            FieldDefinition("load_resistance", "Carga R", "50", unit="Ω"),
        ),
        constraint_fields=_fields(
            FieldDefinition("voltage_ripple_pct", "Rizo máximo Vo", "5", unit="%", is_constraint=True),
        ),
    ),
    TopologyId.AC_AC_TRIAC: TopologyForm(
        topology_id=TopologyId.AC_AC_TRIAC,
        title="Control de fase TRIAC",
        description="Regulador monofásico con TRIAC",
        fields=_fields(
            FieldDefinition("vac_rms", "Vac RMS", "120", unit="V"),
            FieldDefinition("freq_ac", "Frecuencia red", "60", unit="Hz"),
            FieldDefinition("load_resistance", "Carga R", "100", unit="Ω"),
            FieldDefinition("alpha_deg", "Ángulo de disparo", "90", unit="°", allow_zero=True),
        ),
    ),
    TopologyId.DC_AC_HALF_BRIDGE: TopologyForm(
        topology_id=TopologyId.DC_AC_HALF_BRIDGE,
        title="Inversor medio puente",
        description="Inversor DC-AC monofásico",
        fields=_fields(
            FieldDefinition("vdc", "Vdc", "400", unit="V"),
            FieldDefinition("vo_rms", "Vo RMS", "120", unit="V"),
            FieldDefinition("fo", "Frecuencia fundamental", "50", unit="Hz"),
            FieldDefinition("fsw", "Frecuencia de conmutación", "10000", unit="Hz"),
            FieldDefinition("po", "Potencia de salida", "1000", unit="W"),
            FieldDefinition("thd_target", "THD objetivo", "5", unit="%"),
        ),
    ),
    TopologyId.DC_AC_FULL_BRIDGE_SINGLE: TopologyForm(
        topology_id=TopologyId.DC_AC_FULL_BRIDGE_SINGLE,
        title="Inversor puente completo monofásico",
        description="Inversor SPWM clásico",
        fields=_fields(
            FieldDefinition("vdc", "Vdc", "400", unit="V"),
            FieldDefinition("vo_rms", "Vo RMS", "230", unit="V"),
            FieldDefinition("fo", "Frecuencia fundamental", "50", unit="Hz"),
            FieldDefinition("fsw", "Frecuencia de conmutación", "10000", unit="Hz"),
            FieldDefinition("po", "Potencia", "1500", unit="W"),
        ),
    ),
    TopologyId.DC_AC_FULL_BRIDGE_THREE: TopologyForm(
        topology_id=TopologyId.DC_AC_FULL_BRIDGE_THREE,
        title="Inversor trifásico",
        description="Puente completo trifásico",
        fields=_fields(
            FieldDefinition("vdc", "Vdc", "700", unit="V"),
            FieldDefinition("vll_rms", "VLL RMS", "400", unit="V"),
            FieldDefinition("fo", "Frecuencia fundamental", "50", unit="Hz"),
            FieldDefinition("fsw", "Frecuencia de conmutación", "8000", unit="Hz"),
            FieldDefinition("po", "Potencia", "3000", unit="W"),
        ),
    ),
    TopologyId.DC_AC_MODULATION: TopologyForm(
        topology_id=TopologyId.DC_AC_MODULATION,
        title="Modulación PWM",
        description="Parámetros de modulaciones SPWM/SVPWM",
        fields=_fields(
            FieldDefinition("carrier_freq", "Frecuencia portadora", "10000", unit="Hz"),
            FieldDefinition("fundamental_freq", "Frecuencia fundamental", "50", unit="Hz"),
            FieldDefinition("modulation_index", "Índice de modulación", "0.8", unit="", allow_zero=True),
        ),
    ),
}


def available_forms(topologies: Iterable[TopologyId]) -> List[TopologyForm]:
    return [FORMS[topology] for topology in topologies if topology in FORMS]
