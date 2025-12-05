"""Adapter to connect Gradio UI with the application logic."""

import logging
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import asdict

from tutor_virtual.application.services.design_workflow import DesignWorkflowService, ValidationFailedError
from tutor_virtual.application.services.component_recommendation import ComponentRecommendationService
from tutor_virtual.domain.converters import ConverterFactory, TopologyId, register_default_designers
from tutor_virtual.domain.validation import ValidationEngine, register_default_rules
from tutor_virtual.domain.components import ComponentRequirements, ComponentType, Component, PrioritizationWeights
from tutor_virtual.domain.components.selector import ComponentSelector
from tutor_virtual.infrastructure.catalogs.mouser import MouserAdapter
from tutor_virtual.shared.dto import ConverterSpec, DesignContext, DesignRequest, DesignSessionResult
from .spec_schema import FieldDefinition, TopologyForm, available_forms, FORMS

logger = logging.getLogger(__name__)

# Mapeo de variables de salida a sus unidades (reutilizado de app.py)
OUTPUT_UNITS = {
    "vo_avg": "V", "vo_rms": "V", "vo_peak": "V", "vo_min": "V", "vo_max": "V",
    "vripple": "V", "vdc": "V", "vin": "V", "vout": "V",
    "io_avg": "A", "io_rms": "A", "io_peak": "A", "il_avg": "A", "il_rms": "A",
    "il_peak": "A", "il_min": "A", "il_max": "A", "delta_il": "A",
    "inductance": "H", "capacitance": "F", "required_capacitance": "F",
    "l_min": "H", "c_min": "F", "l1": "H", "l2": "H", "lm": "H", "coupling_cap": "F",
    "piv": "V", "peak_inverse_voltage": "V", "max_switch_voltage": "V", "max_diode_voltage": "V",
    "duty_cycle": "", "duty": "", "fsw": "Hz", "frequency": "Hz",
    "power": "W", "power_out": "W", "power_in": "W", "efficiency": "%",
    "losses": "W", "conduction_loss": "W", "switching_loss": "W", "core_loss": "W",
    "copper_loss": "W", "diode_loss": "W", "mosfet_loss": "W", "total_loss": "W",
    "turns_ratio": "", "np": "", "ns": "",
    "thd": "%", "modulation_index": "",
    "form_factor": "", "ripple_factor": "", "rectification_efficiency": "%",
}

COMPONENT_COLUMNS = ["Tipo", "Fabricante", "Número de Parte", "Descripción", "Precio (USD)", "Stock", "Score", "Datasheet", "Link"]

def _create_empty_df(message: str = "") -> pd.DataFrame:
    """Creates an empty DataFrame with the correct columns, optionally with a message."""
    df = pd.DataFrame(columns=COMPONENT_COLUMNS)
    if message:
        # Add a row with the message in the Description column
        row = {col: "" for col in COMPONENT_COLUMNS}
        row["Descripción"] = message
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    return df

def _format_value_with_unit(key: str, value: float) -> str:
    """Formatea un valor con su unidad correspondiente."""
    unit = OUTPUT_UNITS.get(key, "")
    if unit == "F":
        if abs(value) < 1e-6: return f"{value*1e9:.3f} nF"
        elif abs(value) < 1e-3: return f"{value*1e6:.3f} µF"
        elif abs(value) < 1: return f"{value*1e3:.3f} mF"
        else: return f"{value:.6f} F"
    elif unit == "H":
        if abs(value) < 1e-6: return f"{value*1e9:.3f} nH"
        elif abs(value) < 1e-3: return f"{value*1e6:.3f} µH"
        elif abs(value) < 1: return f"{value*1e3:.3f} mH"
        else: return f"{value:.6f} H"
    elif unit == "Hz":
        if abs(value) >= 1e6: return f"{value/1e6:.3f} MHz"
        elif abs(value) >= 1e3: return f"{value/1e3:.3f} kHz"
        else: return f"{value:.3f} Hz"
    elif unit == "%":
        return f"{value:.2f}%"
    elif unit:
        return f"{value:.4g} {unit}"
    else:
        return f"{value:.4g}"

class GradioAdapter:
    def __init__(self):
        self.factory = ConverterFactory()
        register_default_designers(self.factory)
        
        self.validator = ValidationEngine()
        register_default_rules(self.validator)
        
        self.workflow = DesignWorkflowService(factory=self.factory, validation_engine=self.validator)
        self.workflow.factory = self.factory

        self.mouser_adapter = None
        self.component_service = None
        try:
            self.mouser_adapter = MouserAdapter()
            self.component_service = ComponentRecommendationService(
                catalogs=[self.mouser_adapter],
                cache=None
            )
            logger.info("Mouser adapter initialized successfully")
        except Exception as e:
            logger.error(f"Mouser API not available: {e}")

    def get_available_topologies(self) -> List[Tuple[str, str]]:
        """Returns list of (Display Name, ID) for Dropdown."""
        forms = available_forms([info.topology_id for info in self.factory.available_topologies()])
        return [(form.title, form.topology_id.value) for form in forms]

    def get_all_field_keys(self) -> List[str]:
        """Returns a set of all unique field keys across all topologies."""
        keys = set()
        for form in FORMS.values():
            for field in form.fields:
                keys.add(field.key)
            for field in form.constraint_fields:
                keys.add(field.key)
        return list(keys)

    def get_topology_fields(self, topology_id_str: str) -> List[str]:
        """Returns list of field keys active for a given topology."""
        if not topology_id_str:
            return []
        try:
            topology_id = TopologyId(topology_id_str)
            form = FORMS.get(topology_id)
            if not form:
                return []
            keys = [f.key for f in form.fields]
            keys.extend([f.key for f in form.constraint_fields])
            return keys
        except ValueError:
            return []

    def get_topology_defaults(self, topology_id_str: str) -> Dict[str, float]:
        """Returns default values for fields of a given topology."""
        if not topology_id_str:
            return {}
        try:
            topology_id = TopologyId(topology_id_str)
            form = FORMS.get(topology_id)
            if not form:
                return {}
            defaults = {}
            for field in list(form.fields) + list(form.constraint_fields):
                # Use default if set, otherwise try to parse placeholder as default value
                val_to_parse = field.default if field.default is not None else field.placeholder
                
                if val_to_parse is not None:
                    try:
                        defaults[field.key] = float(val_to_parse)
                    except ValueError:
                        pass
            return defaults
        except ValueError:
            return {}

    async def run_design(
        self, 
        topology_id_str: str, 
        inputs: Dict[str, float], 
        weights: Dict[str, float]
    ) -> Tuple[str, pd.DataFrame]:
        """
        Executes the design workflow and component search.
        Returns:
            - Markdown report string
            - Pandas DataFrame with component recommendations
        """
        if not topology_id_str:
            return "⚠️ Por favor seleccione una topología.", _create_empty_df()

        try:
            topology_id = TopologyId(topology_id_str)
            form = FORMS[topology_id]
            
            # Separate operating conditions and constraints
            operating = {}
            constraints = {}
            
            # Map inputs to spec based on form definition
            for field in form.fields:
                if field.key in inputs and inputs[field.key] is not None:
                    operating[field.key] = float(inputs[field.key])
            
            for field in form.constraint_fields:
                if field.key in inputs and inputs[field.key] is not None:
                    constraints[field.key] = float(inputs[field.key])

            spec = ConverterSpec(
                topology_id=topology_id.value,
                operating_conditions=operating,
                constraints=constraints,
            )
            
            context = DesignContext(user_id="gradio-user", project_id="web-session")
            result = self.workflow.run_predesign(DesignRequest(context=context, spec=spec))
            
            # Generate Report
            report = self._generate_markdown_report(result)
            
            # Search Components
            components_df = await self._search_components_df(result, weights)
            
            return report, components_df

        except ValidationFailedError as exc:
            issues = "\n".join(f"- {issue.message}" for issue in exc.issues)
            return f"### ⛔ Error de Validación\n\n{issues}", _create_empty_df()
        except Exception as exc:
            logger.exception("Error running design")
            return f"### ❌ Error del Sistema\n\n{str(exc)}", _create_empty_df()

    def _generate_markdown_report(self, result: DesignSessionResult) -> str:
        lines = ["# 📊 Resultado del Prediseño"]
        
        if result.predesign.primary_values:
            lines.append("## ⚡ Parámetros Principales")
            for key, value in result.predesign.primary_values.items():
                formatted = _format_value_with_unit(key, value)
                name = key.replace("_", " ").title()
                lines.append(f"- **{name}:** {formatted}")
        
        if result.losses.totals and any(result.losses.totals.values()):
            lines.append("\n## 🔥 Pérdidas Estimadas")
            total_losses = 0
            for key, value in result.losses.totals.items():
                formatted = _format_value_with_unit(key, value)
                name = key.replace("_", " ").title()
                lines.append(f"- **{name}:** {formatted}")
                if "loss" in key.lower():
                    total_losses += value
            if total_losses > 0:
                lines.append(f"- **Pérdidas Totales:** {_format_value_with_unit('total_loss', total_losses)}")

        if result.issues:
            lines.append("\n## ⚠️ Advertencias")
            for issue in result.issues:
                icon = "🔴" if issue.severity.value == "error" else "🟡"
                lines.append(f"- {icon} **{issue.severity.value.upper()}:** {issue.message}")
        
        return "\n".join(lines)

    async def _search_components_df(self, result: DesignSessionResult, weights_dict: Dict[str, float]) -> pd.DataFrame:
        if not self.component_service:
            return _create_empty_df("Servicio de componentes no disponible")

        requirements_list = self._extract_component_requirements(result)
        if not requirements_list:
            return _create_empty_df("No se detectaron componentes necesarios")

        all_components = []
        prioritization = PrioritizationWeights(**weights_dict)
        selector = ComponentSelector(weights=prioritization)

        for req in requirements_list:
            try:
                components = []
                for catalog in self.component_service.catalogs:
                    found = await catalog.search_components(requirements=req, limit=5)
                    components.extend(found)
                
                if components:
                    scored = selector.select_top_components(components, req, top_n=5)
                    for s in scored:
                        c = s.component
                        # Format links as HTML for Gradio Dataframe
                        datasheet_link = f'<a href="{c.datasheet_url}" target="_blank">PDF</a>' if c.datasheet_url else "-"
                        product_link = f'<a href="{c.product_url}" target="_blank">Ver</a>' if c.product_url else "-"
                        
                        all_components.append({
                            "Tipo": req.component_type.value,
                            "Fabricante": c.manufacturer,
                            "Número de Parte": c.part_number,
                            "Descripción": c.description,
                            "Precio (USD)": c.price_usd,
                            "Stock": c.availability,
                            "Score": f"{s.total_score:.2f}",
                            "Datasheet": datasheet_link,
                            "Link": product_link
                        })
            except Exception as e:
                logger.error(f"Error searching components for {req.component_type}: {e}")

        if not all_components:
            return _create_empty_df("No se encontraron componentes")

        df = pd.DataFrame(all_components)
        # Ensure columns are in the correct order
        df = df[COMPONENT_COLUMNS]
        # Fill NaN values to avoid JSON serialization errors
        df = df.fillna("")
        return df

    def _extract_component_requirements(self, result: DesignSessionResult) -> List[ComponentRequirements]:
        # Logic copied and adapted from app.py
        requirements_list = []
        primary = result.predesign.primary_values
        topology = TopologyId(result.spec.topology_id)
        
        topology_components = {
            TopologyId.DC_DC_BUCK: [ComponentType.MOSFET, ComponentType.DIODE, ComponentType.INDUCTOR, ComponentType.CAPACITOR],
            TopologyId.DC_DC_BOOST: [ComponentType.MOSFET, ComponentType.DIODE, ComponentType.INDUCTOR, ComponentType.CAPACITOR],
            TopologyId.DC_DC_BUCK_BOOST: [ComponentType.MOSFET, ComponentType.DIODE, ComponentType.INDUCTOR, ComponentType.CAPACITOR],
            TopologyId.DC_DC_CUK: [ComponentType.MOSFET, ComponentType.DIODE, ComponentType.INDUCTOR, ComponentType.CAPACITOR],
            TopologyId.DC_DC_FLYBACK: [ComponentType.MOSFET, ComponentType.DIODE, ComponentType.CAPACITOR],
            TopologyId.AC_DC_RECTIFIER_SINGLE: [ComponentType.DIODE, ComponentType.CAPACITOR],
            TopologyId.AC_DC_RECTIFIER_FULL: [ComponentType.DIODE, ComponentType.CAPACITOR],
            TopologyId.DC_AC_HALF_BRIDGE: [ComponentType.MOSFET, ComponentType.CAPACITOR],
            TopologyId.DC_AC_FULL_BRIDGE_SINGLE: [ComponentType.MOSFET, ComponentType.CAPACITOR],
            TopologyId.DC_AC_FULL_BRIDGE_THREE: [ComponentType.MOSFET, ComponentType.CAPACITOR],
        }
        
        component_types = topology_components.get(topology, [])
        operating = result.spec.operating_conditions
        
        voltage_max = (
            operating.get("vin") or operating.get("vdc") or operating.get("vin_max") or
            primary.get("vin") or primary.get("vdc") or primary.get("vo_avg") or primary.get("vac_rms", 0)
        )
        if voltage_max: voltage_max *= 1.5
        
        current_max = (
            operating.get("io_max") or operating.get("io") or
            primary.get("io_max") or primary.get("il_avg") or primary.get("io_avg") or primary.get("i_l_rms", 0)
        )
        if current_max: current_max *= 1.2
        
        inductance = primary.get("inductance") or primary.get("l_min")
        capacitance = primary.get("capacitance") or primary.get("c_min") or primary.get("required_capacitance")
        
        for comp_type in component_types:
            req = ComponentRequirements(
                component_type=comp_type,
                voltage_max=voltage_max if voltage_max else None,
                current_max=current_max if current_max else None,
                inductance_min=inductance if comp_type == ComponentType.INDUCTOR and inductance else None,
                capacitance_min=capacitance if comp_type == ComponentType.CAPACITOR and capacitance else None,
            )
            requirements_list.append(req)
            
        return requirements_list
