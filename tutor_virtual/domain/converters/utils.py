"""Utility helpers for converter designer implementations."""

from __future__ import annotations

from math import pi, sqrt
from typing import Mapping

from ...shared.dto import ConverterSpec


def require(
    spec: ConverterSpec,
    key: str,
    *,
    allow_negative: bool = False,
    allow_zero: bool = False,
) -> float:
    """Fetch a required numeric value from the operating conditions."""

    try:
        value = spec.operating_conditions[key]
    except KeyError as exc:
        raise KeyError(f"Missing required spec value: {key}") from exc
    if not isinstance(value, (int, float)):
        raise ValueError(f"Specification value '{key}' must be numeric")
    if value == 0 and not allow_zero:
        raise ValueError(f"Specification value '{key}' must be non-zero")
    if value < 0 and not allow_negative:
        raise ValueError(f"Specification value '{key}' must be positive")
    return float(value)


def get_optional(
    spec: ConverterSpec,
    key: str,
    default: float | None = None,
    *,
    allow_zero: bool = False,
) -> float:
    """Return an optional numeric value from the spec operating conditions."""

    if key not in spec.operating_conditions:
        if default is None:
            raise KeyError(f"Missing optional spec value: {key}")
        return default
    value = spec.operating_conditions[key]
    if not isinstance(value, (int, float)):
        raise ValueError(f"Specification value '{key}' must be numeric")
    if value <= 0 and not allow_zero:
        raise ValueError(f"Specification value '{key}' must be positive")
    return float(value)


def percentage_to_fraction(value: float | int) -> float:
    """Convert a percentage (e.g. 5 for 5%) to a fraction (0.05)."""

    return float(value) / 100.0


def rms_from_peak(peak: float) -> float:
    return peak / sqrt(2.0)


def triangular_rms(current_avg: float, ripple: float) -> float:
    """RMS of a triangular waveform around current_avg with peak-to-peak ripple."""

    return (current_avg**2 + (ripple**2) / 12.0) ** 0.5


def capacitor_ripple_current(delta_il: float) -> float:
    """Approximate capacitor RMS current for buck-derived converters."""

    return delta_il / (2.0 * sqrt(3.0))


def sin_deg(angle_deg: float) -> float:
    from math import sin, radians

    return sin(radians(angle_deg))


def cos_deg(angle_deg: float) -> float:
    from math import cos, radians

    return cos(radians(angle_deg))


def fundamental_modulation_index(v_ref: float, v_dc: float) -> float:
    return min(max(v_ref / (v_dc / 2.0), 0.0), 1.0)


def ensure_keys(spec: ConverterSpec, *keys: str) -> list[str]:
    missing = [key for key in keys if key not in spec.operating_conditions]
    return missing
