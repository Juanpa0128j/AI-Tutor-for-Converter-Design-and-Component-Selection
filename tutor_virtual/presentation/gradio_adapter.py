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
from .translations import get_text

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

def _create_empty_df(message: str = "", lang_label: str = "Español") -> pd.DataFrame:
    """Creates an empty DataFrame with the correct columns, optionally with a message."""
    cols = [
        get_text("col_type", lang_label),
        get_text("col_mfr", lang_label),
        get_text("col_part", lang_label),
        get_text("col_desc", lang_label),
        get_text("col_price", lang_label),
        get_text("col_stock", lang_label),
        get_text("col_score", lang_label),
        get_text("col_datasheet", lang_label),
        get_text("col_link", lang_label)
    ]
    df = pd.DataFrame(columns=cols)
    if message:
        # Add a row with the message in the Description column
        row = {col: "" for col in cols}
        row[get_text("col_desc", lang_label)] = message
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
        self.task_queue = None
        
        try:
            from tutor_virtual.infrastructure.task_queue import RedisTaskQueue
            self.task_queue = RedisTaskQueue()
            logger.info("Redis Task Queue initialized")
        except Exception as e:
            logger.warning(f"Redis Task Queue not available: {e}")

        try:
            self.mouser_adapter = MouserAdapter()
            self.component_service = ComponentRecommendationService(
                catalogs=[self.mouser_adapter],
                cache=None
            )
            logger.info("Mouser adapter initialized successfully")
        except Exception as e:
            logger.error(f"Mouser API not available: {e}")

    def submit_indexing_job(self, file_path: str, original_filename: str, strategy: str = "fast") -> str:
        """Submit a document indexing job to the background queue."""
        if not self.task_queue:
            raise RuntimeError("Task queue is not available (Redis not configured?)")
            
        import shutil
        import os
        from pathlib import Path
        
        # Create staging directory
        staging_dir = Path("data/uploads/staging")
        staging_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy file to staging area so worker can access it
        staging_path = staging_dir / f"{os.path.basename(file_path)}"
        shutil.copy2(file_path, staging_path)
        
        job_id = self.task_queue.enqueue_job(
            "index_document",
            {
                "file_path": str(staging_path.absolute()),
                "original_filename": original_filename,
                "strategy": strategy
            }
        )
        return job_id

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of a background job."""
        if not self.task_queue:
            return {"status": "unknown"}
        return self.task_queue.get_job_status(job_id)

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document via the RAG service."""
        from tutor_virtual.infrastructure.rag import get_rag_service
        try:
            service = get_rag_service()
            return service.delete_document(doc_id)
        except Exception as e:
            logger.error(f"Error deleting document via adapter: {e}")
            return False

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
        weights: Dict[str, float],
        lang_label: str = "Español"
    ) -> Tuple[str, pd.DataFrame, Optional[Dict[str, Any]]]:
        """
        Executes the design workflow and component search.
        Returns:
            - Markdown report string
            - Pandas DataFrame with component recommendations
            - Dictionary with raw design result for context
        """
        if not topology_id_str:
            return get_text("msg_select_topo", lang_label), _create_empty_df(get_text("msg_select_topo", lang_label)), None

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
            report = self._generate_markdown_report(result, lang_label)
            
            # Search Components
            components_df, components_list = await self._search_components_df(result, weights, lang_label)
            
            # Convert result to dict for context
            # We use a custom serialization or just extract what we need to avoid issues with Enums/complex types
            # For now, let's try to construct a safe dict
            result_context = {
                "topology": result.spec.topology_id,
                "inputs": result.spec.operating_conditions,
                "calculated_values": result.predesign.primary_values,
                "losses": result.losses.totals if result.losses else {},
                "recommendation": result.recommendation.summary if result.recommendation else "",
                "components": components_list
            }
            
            return report, components_df, result_context

        except ValidationFailedError as exc:
            issues = "\n".join(f"- {issue.message}" for issue in exc.issues)
            title = get_text("report_error_validation", lang_label)
            return f"### ⛔ {title}\n\n{issues}", _create_empty_df(title), None
        except Exception as exc:
            logger.exception("Error running design")
            title = get_text("report_error_system", lang_label)
            return f"### ❌ {title}\n\n{str(exc)}", _create_empty_df(title), None

    def _generate_markdown_report(self, result: DesignSessionResult, lang_label: str) -> str:
        lines = [f"# 📊 {get_text('report_title', lang_label)}"]
        
        if result.predesign.primary_values:
            lines.append(f"## ⚡ {get_text('report_params', lang_label)}")
            for key, value in result.predesign.primary_values.items():
                formatted = _format_value_with_unit(key, value)
                name = key.replace("_", " ").title()
                lines.append(f"- **{name}:** {formatted}")
        
        if result.losses.totals and any(result.losses.totals.values()):
            lines.append(f"\n## 🔥 {get_text('report_losses', lang_label)}")
            total_losses = 0
            for key, value in result.losses.totals.items():
                formatted = _format_value_with_unit(key, value)
                name = key.replace("_", " ").title()
                lines.append(f"- **{name}:** {formatted}")
                if "loss" in key.lower():
                    total_losses += value
            if total_losses > 0:
                lines.append(f"- **{get_text('report_total_losses', lang_label)}:** {_format_value_with_unit('total_loss', total_losses)}")

        if result.issues:
            lines.append(f"\n## ⚠️ {get_text('report_warnings', lang_label)}")
            for issue in result.issues:
                icon = "🔴" if issue.severity.value == "error" else "🟡"
                lines.append(f"- {icon} **{issue.severity.value.upper()}:** {issue.message}")
        
        return "\n".join(lines)

    async def _search_components_df(self, result: DesignSessionResult, weights_dict: Dict[str, float], lang_label: str) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        if not self.component_service:
            return _create_empty_df(get_text("comp_service_unavailable", lang_label), lang_label), []

        requirements_list = self._extract_component_requirements(result)
        if not requirements_list:
            return _create_empty_df(get_text("comp_no_requirements", lang_label), lang_label), []

        all_components = []
        raw_components_data = []
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
                        view_text = get_text("link_view", lang_label)
                        product_link = f'<a href="{c.product_url}" target="_blank">{view_text}</a>' if c.product_url else "-"
                        
                        all_components.append({
                            get_text("col_type", lang_label): req.component_type.value,
                            get_text("col_mfr", lang_label): c.manufacturer,
                            get_text("col_part", lang_label): c.part_number,
                            get_text("col_desc", lang_label): c.description,
                            get_text("col_price", lang_label): c.price_usd,
                            get_text("col_stock", lang_label): c.availability,
                            get_text("col_score", lang_label): round(s.total_score, 2),
                            get_text("col_datasheet", lang_label): datasheet_link,
                            get_text("col_link", lang_label): product_link
                        })
                        
                        # Add raw data for agent
                        # Convert dataclass to dict, excluding private fields
                        comp_dict = asdict(c)
                        raw_components_data.append({
                            "type": req.component_type.value,
                            "manufacturer": c.manufacturer,
                            "part_number": c.part_number,
                            "description": c.description,
                            "datasheet_url": c.datasheet_url,
                            "attributes": {k: v for k, v in comp_dict.items() if k not in ['part_number', 'manufacturer', 'description', 'datasheet_url', 'product_url', 'catalog', 'price_usd', 'availability']}
                        })

            except Exception as e:
                logger.error(f"Error searching components for {req.component_type}: {e}")

        if not all_components:
            return _create_empty_df(get_text("comp_no_requirements", lang_label), lang_label), []

        df = pd.DataFrame(all_components)
        df = df.fillna("")
        return df, raw_components_data

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
