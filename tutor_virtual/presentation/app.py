"""Textual-based wizard to interact with the design workflow."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from pathlib import Path
import os

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Label, Markdown, Select

from tutor_virtual.application.services.design_workflow import DesignWorkflowService, ValidationFailedError
from tutor_virtual.application.services.component_recommendation import ComponentRecommendationService
from tutor_virtual.domain.converters import ConverterFactory, TopologyId, register_default_designers
from tutor_virtual.domain.validation import ValidationEngine, register_default_rules
from tutor_virtual.domain.components import ComponentRequirements, ComponentType, Component, PrioritizationWeights
from tutor_virtual.domain.components.selector import ComponentSelector
from tutor_virtual.infrastructure.catalogs.mouser import MouserAdapter
from tutor_virtual.shared.dto import ConverterSpec, DesignContext, DesignRequest, DesignSessionResult

from .spec_schema import FieldDefinition, TopologyForm, available_forms


# Configure logging - production uses INFO, DEBUG available via env var
log_level = logging.DEBUG if os.getenv("DEBUG") else logging.INFO

# Build handlers - file logging is optional via LOG_TO_FILE env var
handlers = [logging.StreamHandler()]
if os.getenv("LOG_TO_FILE"):
    log_file = Path(__file__).parent.parent.parent / "component_search.log"
    handlers.append(logging.FileHandler(log_file, mode='w'))

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)

# Silence noisy third-party loggers
logging.getLogger('markdown_it').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# Mapeo de variables de salida a sus unidades
OUTPUT_UNITS = {
    # Voltajes
    "vo_avg": "V",
    "vo_rms": "V",
    "vo_peak": "V",
    "vo_min": "V",
    "vo_max": "V",
    "vripple": "V",
    "vdc": "V",
    "vin": "V",
    "vout": "V",
    
    # Corrientes
    "io_avg": "A",
    "io_rms": "A",
    "io_peak": "A",
    "il_avg": "A",
    "il_rms": "A",
    "il_peak": "A",
    "il_min": "A",
    "il_max": "A",
    "delta_il": "A",
    
    # Componentes pasivos
    "inductance": "H",
    "capacitance": "F",
    "required_capacitance": "F",
    "l_min": "H",
    "c_min": "F",
    "l1": "H",
    "l2": "H",
    "lm": "H",
    "coupling_cap": "F",
    
    # Semiconductores
    "piv": "V",
    "peak_inverse_voltage": "V",
    "max_switch_voltage": "V",
    "max_diode_voltage": "V",
    
    # Duty cycle y frecuencias
    "duty_cycle": "",
    "duty": "",
    "fsw": "Hz",
    "frequency": "Hz",
    
    # Potencias y pérdidas
    "power": "W",
    "power_out": "W",
    "power_in": "W",
    "efficiency": "%",
    "losses": "W",
    "conduction_loss": "W",
    "switching_loss": "W",
    "core_loss": "W",
    "copper_loss": "W",
    "diode_loss": "W",
    "mosfet_loss": "W",
    "total_loss": "W",
    
    # Transformador
    "turns_ratio": "",
    "np": "",
    "ns": "",
    
    # THD y modulación
    "thd": "%",
    "modulation_index": "",
    
    # Otros
    "form_factor": "",
    "ripple_factor": "",
    "rectification_efficiency": "%",
}


def _format_value_with_unit(key: str, value: float) -> str:
    """Formatea un valor con su unidad correspondiente."""
    unit = OUTPUT_UNITS.get(key, "")
    
    # Formateo especial para diferentes magnitudes
    if unit == "F":  # Faradios - típicamente muy pequeños
        if abs(value) < 1e-6:
            return f"{value*1e9:.3f} nF"
        elif abs(value) < 1e-3:
            return f"{value*1e6:.3f} µF"
        elif abs(value) < 1:
            return f"{value*1e3:.3f} mF"
        else:
            return f"{value:.6f} F"
    elif unit == "H":  # Henrios
        if abs(value) < 1e-6:
            return f"{value*1e9:.3f} nH"
        elif abs(value) < 1e-3:
            return f"{value*1e6:.3f} µH"
        elif abs(value) < 1:
            return f"{value*1e3:.3f} mH"
        else:
            return f"{value:.6f} H"
    elif unit == "Hz":  # Frecuencias
        if abs(value) >= 1e6:
            return f"{value/1e6:.3f} MHz"
        elif abs(value) >= 1e3:
            return f"{value/1e3:.3f} kHz"
        else:
            return f"{value:.3f} Hz"
    elif unit == "%":
        return f"{value:.2f}%"
    elif unit:
        return f"{value:.4g} {unit}"
    else:
        return f"{value:.4g}"


@dataclass(slots=True)
class FieldState:
    definition: FieldDefinition
    widget: Input

    def value(self) -> str:
        return self.widget.value.strip()


@dataclass(slots=True)
class FormState:
    topology: TopologyForm
    fields: Dict[str, FieldState] = field(default_factory=dict)
    constraint_fields: Dict[str, FieldState] = field(default_factory=dict)

    def to_spec(self) -> ConverterSpec:
        operating: Dict[str, float] = {}
        constraints: Dict[str, float] = {}

        for key, field_state in self.fields.items():
            operating[key] = _parse_numeric(field_state.definition, field_state.value())
        for key, field_state in self.constraint_fields.items():
            constraints[key] = _parse_numeric(field_state.definition, field_state.value())

        return ConverterSpec(
            topology_id=self.topology.topology_id.value,
            operating_conditions=operating,
            constraints=constraints,
        )


def _parse_numeric(defn: FieldDefinition, raw: str) -> float:
    if raw == "" and defn.default is not None:
        raw = str(defn.default)
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"El campo '{defn.label}' requiere un valor numérico") from exc
    if value < 0 and not defn.allow_negative:
        raise ValueError(f"El campo '{defn.label}' debe ser positivo")
    if value == 0 and not defn.allow_zero:
        raise ValueError(f"El campo '{defn.label}' no puede ser cero")
    return value


class RunDesignMessage(Message):
    def __init__(self, form_state: FormState) -> None:
        self.form_state = form_state
        super().__init__()


class DesignWizardApp(App[None]):
    """Textual app that guides users through converter design."""

    CSS = """
    Screen {
        align: center middle;
    }
    #topology-pane {
        width: 30%;
        border: solid $surface-darken-2;
        padding: 1;
    }
    #form-pane {
        width: 70%;
        border: solid $primary 30%;
        padding: 1;
        height: 100%;
        layout: vertical;
    }
    #form-title {
        height: auto;
    }
    #form-scroll {
        scrollbar-size-vertical: 3;
        height: 1fr;
        margin-bottom: 1;
    }
    Label.title {
        margin-bottom: 1;
        text-style: bold;
    }
    .field-label {
        width: 100%;
        padding-bottom: 1;
    }
    .field-input {
        width: 100%;
        margin-bottom: 1;
    }
    #results {
        border: solid $accent;
        background: $surface;
        height: auto;
        max-height: 15;
        overflow-y: auto;
    }
    #form-buttons {
        height: auto;
        align: center middle;
        content-align: center middle;
    }
    #form-buttons > Button {
        margin: 0;
        min-height: 1;
        width: auto;
    }
    #component-catalog {
        border: solid $success;
        background: $surface;
        height: auto;
        max-height: 15;
        padding: 1;
        overflow-y: auto;
    }
    #prioritization-controls {
        border: solid $warning;
        background: $surface-darken-1;
        overflow-y: auto;
        padding: 1;
    }
    .weight-input {
        width: 15;
    }
    .weight-label {
        width: 20;
        margin-left: 1;
    }
    #update-weights-button {
        width: 20;
        min-width: 20;
        height: 1;
        margin: 1;
    }
    #weight-info {
        text-align: center;
        text-style: italic;
    }
    #component-loading {
        text-align: center;
        text-style: italic;
        color: $accent;
    }
    """

    BINDINGS = [
        ("escape,q", "quit", "Salir"),
        ("ctrl+s,f5", "run", "Calcular"),
    ]

    selected_topology: reactive[Optional[TopologyId]] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        container = _build_workflow()
        self._workflow = container.workflow
        self._factory = container.factory
        self._forms = available_forms([info.topology_id for info in self._factory.available_topologies()])
        self._current_form: Optional[FormState] = None
        
        # Initialize component recommendation service with Mouser
        self._mouser_adapter = None
        self._component_service = None
        try:
            self._mouser_adapter = MouserAdapter()
            self._component_service = ComponentRecommendationService(
                catalogs=[self._mouser_adapter],
                cache=None  # No cache for MVP
            )
            logger.info("✅ Mouser adapter initialized successfully")
        except Exception as e:
            logger.error(f"⚠️  Mouser API not available: {e}", exc_info=True)
        
        # Default prioritization weights
        self._current_weights = PrioritizationWeights(
            cost=0.30,
            availability=0.25,
            efficiency=0.25,
            thermal=0.20
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield self._build_topology_panel()
            yield self._build_form_panel()
        yield Footer()

    def _build_topology_panel(self) -> Container:
        options = [(form.title, form.topology_id.value) for form in self._forms]
        select = Select(options=options, prompt="Seleccione topología", id="topology-select")
        prioritization_panel = self._build_prioritization_panel()
        return Container(
            Label("Topologías disponibles", classes="title"),
            select,
            Markdown("Utilice las flechas para navegar y Enter para confirmar."),
            prioritization_panel,
            id="topology-pane",
        )
    
    def _build_prioritization_panel(self) -> Container:
        """Build panel for configuring component prioritization weights."""
        return Container(
            Label("Priorización de Componentes", classes="title"),
            Horizontal(
                Label("Costo:", classes="weight-label"),
                Input(value="0.30", placeholder="0.30", classes="weight-input", id="weight-cost"),
            ),
            Horizontal(
                Label("Disponibilidad:", classes="weight-label"),
                Input(value="0.25", placeholder="0.25", classes="weight-input", id="weight-availability"),
            ),
            Horizontal(
                Label("Eficiencia:", classes="weight-label"),
                Input(value="0.25", placeholder="0.25", classes="weight-input", id="weight-efficiency"),
            ),
            Horizontal(
                Label("Térmica:", classes="weight-label"),
                Input(value="0.20", placeholder="0.20", classes="weight-input", id="weight-thermal"),
            ),
            Markdown("*Los pesos se aplican automáticamente*", id="weight-info"),
            id="prioritization-controls",
        )

    def _build_form_panel(self) -> Container:
        self._form_scroll = VerticalScroll(id="form-scroll")
        self._status = Markdown("Seleccione una topología para comenzar.", id="results")
        self._component_catalog = Markdown("", id="component-catalog")
        buttons = Horizontal(
            Button("Calcular", id="run-button", variant="success"),
            Button("Limpiar", id="clear-button", variant="primary"),
            id="form-buttons",
        )
        return Container(
            Label("Especificaciones", classes="title", id="form-title"),
            self._form_scroll,
            self._status,
            self._component_catalog,
            buttons,
            id="form-pane",
        )

    async def on_mount(self) -> None:
        select = self.query_one("#topology-select", Select)
        select.focus()

    async def on_select_changed(self, event: Select.Changed) -> None:
        topology_value = event.value
        if topology_value is None or topology_value == Select.BLANK:
            # User selected the placeholder/prompt, clear the form
            for child in list(self._form_scroll.children):
                await child.remove()
            self._status.update("Seleccione una topología para comenzar.")
            self.selected_topology = None
            return
        topology = TopologyId(topology_value)
        form_def = next(form for form in self._forms if form.topology_id == topology)
        await self._render_form(form_def)
        self.selected_topology = topology

    async def _render_form(self, form: TopologyForm) -> None:
        # Remove previous widgets to rebuild the form for the selected topology
        for child in list(self._form_scroll.children):
            await child.remove()
        form_state = FormState(topology=form)

        await self._form_scroll.mount(Label(form.description, classes="title"))
        first_focus: Optional[Input] = None
        for field_def in form.fields:
            field_label, field_widget = self._create_field_widgets(field_def)
            await self._form_scroll.mount(field_label, field_widget)
            form_state.fields[field_def.key] = FieldState(definition=field_def, widget=field_widget)
            if first_focus is None:
                first_focus = field_widget
        if form.constraint_fields:
            await self._form_scroll.mount(Label("Restricciones", classes="title"))
            for field_def in form.constraint_fields:
                field_label, field_widget = self._create_field_widgets(field_def)
                await self._form_scroll.mount(field_label, field_widget)
                form_state.constraint_fields[field_def.key] = FieldState(definition=field_def, widget=field_widget)

        self._current_form = form_state
        if first_focus is not None:
            first_focus.focus()
        self._status.update("Ingrese los parámetros y presione Calcular (Ctrl+S).")

    def _create_field_widgets(self, definition: FieldDefinition) -> tuple[Label, Input]:
        # Display units prominently in the label
        label_text = definition.label
        if definition.unit:
            label_text = f"{definition.label} ({definition.unit})"
        label = Label(label_text, classes="field-label")
        input_widget = Input(placeholder=definition.placeholder or "", classes="field-input")
        if definition.default is not None:
            input_widget.value = str(definition.default)
        return label, input_widget

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-button":
            await self._handle_run()
        elif event.button.id == "clear-button":
            await self._handle_clear()

    async def action_run(self) -> None:
        await self._handle_run()

    async def _handle_run(self) -> None:
        if not self._current_form:
            self.bell()
            self._status.update("Seleccione una topología antes de calcular.")
            return
        try:
            spec = self._current_form.to_spec()
            context = DesignContext(user_id="demo", project_id="demo-project")
            result = self._workflow.run_predesign(DesignRequest(context=context, spec=spec))
        except ValidationFailedError as exc:
            issues = "\n".join(f"- {issue.message}" for issue in exc.issues)
            self._status.update(f"Validación bloqueante:\n{issues}")
            self.bell()
            return
        except Exception as exc:  # pragma: no cover - UI feedback
            self._status.update(f"Error: {exc}")
            self.bell()
            return

        # Formatear resultados de forma estética con unidades
        lines = ["# 📊 RESULTADO DEL PREDISEÑO"]
        
        # Parámetros principales
        if result.predesign.primary_values:
            lines.append("## ⚡ PARÁMETROS PRINCIPALES")
            for key, value in result.predesign.primary_values.items():
                formatted_value = _format_value_with_unit(key, value)
                # Hacer el nombre más legible
                display_name = key.replace("_", " ").title()
                lines.append(f"**• {display_name}:** {formatted_value}")
                lines.append("")  # Línea vacía entre items
        
        # Pérdidas estimadas - solo mostrar si hay datos
        if result.losses.totals and any(result.losses.totals.values()):
            lines.append("## 🔥 PÉRDIDAS ESTIMADAS")
            total_losses = 0
            for key, value in result.losses.totals.items():
                formatted_value = _format_value_with_unit(key, value)
                display_name = key.replace("_", " ").title()
                lines.append(f"**• {display_name}:** {formatted_value}")
                lines.append("")  # Línea vacía entre items
                if "loss" in key.lower():
                    total_losses += value
            if total_losses > 0:
                lines.append(f"**Pérdidas Totales:** {_format_value_with_unit('total_loss', total_losses)}")
        
        # Advertencias
        if result.issues:
            lines.append("## ⚠️ ADVERTENCIAS")
            for issue in result.issues:
                severity_emoji = "🔴" if issue.severity.value == "error" else "🟡"
                lines.append(f"**{severity_emoji} {issue.severity.value.upper()}:** {issue.message}")
                lines.append("")  # Línea vacía entre items
        
        self._status.update("\n".join(lines))
        
        # Search for recommended components
        if self._component_service:
            await self._search_components(result)
        else:
            self._component_catalog.update("## 🔌 COMPONENTES RECOMENDADOS\n\nComponentes no disponibles en este momento.")

    async def _handle_clear(self) -> None:
        if not self._current_form:
            return
        for field_state in list(self._current_form.fields.values()) + list(self._current_form.constraint_fields.values()):
            field_state.widget.value = str(field_state.definition.default or "")
        self._status.update("Campos reiniciados. Modifique valores y ejecute nuevamente.")
        self._component_catalog.update("")
    
    def _get_current_weights(self) -> PrioritizationWeights:
        """Read prioritization weights from UI inputs."""
        try:
            cost = float(self.query_one("#weight-cost", Input).value)
            availability = float(self.query_one("#weight-availability", Input).value)
            efficiency = float(self.query_one("#weight-efficiency", Input).value)
            thermal = float(self.query_one("#weight-thermal", Input).value)
            
            # Validate sum equals 1.0
            total = cost + availability + efficiency + thermal
            if abs(total - 1.0) > 0.01:
                logger.warning(f"⚠️  Pesos no suman 1.0 (actual: {total:.2f}), usando valores por defecto")
                return self._current_weights  # Return defaults
            
            # Create new weights
            return PrioritizationWeights(
                cost=cost,
                availability=availability,
                efficiency=efficiency,
                thermal=thermal
            )
            
        except ValueError as e:
            logger.warning(f"⚠️  Error leyendo pesos: {e}, usando valores por defecto")
            return self._current_weights  # Return defaults
    
    async def _search_components(self, result: DesignSessionResult) -> None:
        """Search for recommended components based on design results."""
        self._component_catalog.update("## 🔌 COMPONENTES RECOMENDADOS\n\n🔄 **Buscando componentes...**")
        
        try:
            # Determine component requirements from design results
            requirements_list = self._extract_component_requirements(result)
            
            if not requirements_list:
                self._component_catalog.update("## 🔌 COMPONENTES RECOMENDADOS\n\nNo se detectaron componentes necesarios para esta topología.")
                return
            
            all_components = []
            
            # Search for each component type
            for idx, requirements in enumerate(requirements_list, 1):
                try:
                    # Note: recommend_components expects different parameters
                    # For now, search directly through catalogs
                    components = []
                    for catalog in self._component_service.catalogs:
                        try:
                            catalog_components = await catalog.search_components(
                                requirements=requirements,
                                limit=5
                            )
                            components.extend(catalog_components)
                        except Exception as catalog_error:
                            pass  # Silently skip catalog errors
                    
                    # Apply prioritization with current weights from UI
                    if components:
                        # Read current weights from UI inputs
                        current_weights = self._get_current_weights()
                        selector = ComponentSelector(weights=current_weights)
                        scored = selector.select_top_components(
                            components=components,
                            requirements=requirements,
                            top_n=5
                        )
                        components = [score.component for score in scored]
                    all_components.extend(components)
                except Exception as e:
                    pass  # Silently skip component type errors
            
            # Format results
            if all_components:
                catalog_md = self._format_component_catalog(all_components)
                self._component_catalog.update(catalog_md)
            else:
                self._component_catalog.update("## 🔌 COMPONENTES RECOMENDADOS\n\nNo se encontraron componentes que cumplan los requisitos.")
        
        except Exception as e:
            logger.error(f"❌ ERROR CRÍTICO en búsqueda de componentes: {type(e).__name__}: {e}", exc_info=True)
            self._component_catalog.update("## 🔌 COMPONENTES RECOMENDADOS\n\nComponentes no disponibles en este momento.")
    
    def _extract_component_requirements(self, result: DesignSessionResult) -> List[ComponentRequirements]:
        """Extract component requirements from design session result."""
        requirements_list = []
        primary = result.predesign.primary_values
        topology = TopologyId(result.spec.topology_id)
        
        logger.debug(f"\n🔧 Extracting requirements for topology: {topology.value}")
        logger.debug(f"📊 Primary values from pre-design:")
        for key, value in primary.items():
            logger.debug(f"   {key}: {value}")
        
        # Map topology to required component types
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
        logger.debug(f"\n🎯 Required components: {[ct.value for ct in component_types]}")
        
        # Extract voltage and current from operating conditions (input) and results
        operating = result.spec.operating_conditions
        
        # Voltage: prefer input specs, fallback to calculated values
        voltage_max = (
            operating.get("vin") or 
            operating.get("vdc") or 
            operating.get("vin_max") or
            primary.get("vin") or 
            primary.get("vdc") or 
            primary.get("vo_avg") or 
            primary.get("vac_rms", 0)
        )
        voltage_original = voltage_max
        if voltage_max:
            voltage_max *= 1.5  # Safety margin
        
        # Current: prefer input specs, fallback to calculated values
        current_max = (
            operating.get("io_max") or
            operating.get("io") or
            primary.get("io_max") or 
            primary.get("il_avg") or 
            primary.get("io_avg") or
            primary.get("i_l_rms", 0)
        )
        current_original = current_max
        if current_max:
            current_max *= 1.2  # Safety margin
        
        inductance = primary.get("inductance") or primary.get("l_min")
        capacitance = primary.get("capacitance") or primary.get("c_min") or primary.get("required_capacitance")
        
        logger.debug(f"\n⚡ Extracted values:")
        logger.debug(f"   Voltage: {voltage_original}V → {voltage_max}V (with 1.5x margin)")
        logger.debug(f"   Current: {current_original}A → {current_max}A (with 1.2x margin)")
        logger.debug(f"   Inductance: {inductance*1e6 if inductance else 0:.2f}µH")
        logger.debug(f"   Capacitance: {capacitance*1e6 if capacitance else 0:.2f}µF")
        
        # Create requirements for each component type
        for comp_type in component_types:
            req = ComponentRequirements(
                component_type=comp_type,
                voltage_max=voltage_max if voltage_max else None,
                current_max=current_max if current_max else None,
                inductance_min=inductance if comp_type == ComponentType.INDUCTOR and inductance else None,
                capacitance_min=capacitance if comp_type == ComponentType.CAPACITOR and capacitance else None,
            )
            requirements_list.append(req)
            logger.debug(f"   ✓ Created requirement for {comp_type.value}")
        
        return requirements_list
    
    def _format_component_catalog(self, components: List[Component]) -> str:
        """Format component list as Markdown catalog with detailed specifications."""
        lines = ["## 🔌 COMPONENTES RECOMENDADOS\n"]
        
        # Group by component type using actual class names
        by_type: Dict[str, List[Component]] = {}
        for comp in components:
            # Get the actual class name (MOSFET, Diode, Capacitor, Inductor)
            comp_type = type(comp).__name__
            if comp_type not in by_type:
                by_type[comp_type] = []
            by_type[comp_type].append(comp)
        
        # Format each group with proper type names
        type_names = {
            "MOSFET": "MOSFETs",
            "Diode": "Diodos",
            "Capacitor": "Capacitores",
            "Inductor": "Inductores",
            "Component": "Componentes"
        }
        
        for comp_type, comp_list in by_type.items():
            display_name = type_names.get(comp_type, f"{comp_type}s")
            lines.append(f"### {display_name}\n")
            
            for i, comp in enumerate(comp_list[:5], 1):  # Max 5 per type
                lines.append(f"**{i}. {comp.manufacturer} - {comp.part_number}**")
                
                # Description (truncated if too long)
                if comp.description:
                    desc = comp.description[:80] + "..." if len(comp.description) > 80 else comp.description
                    lines.append(f"   {desc}")
                
                # Price and availability
                lines.append(f"   **Precio:** ${comp.price_usd:.2f} | **Stock:** {comp.availability} unidades")
                
                # MOSFET specific specs
                if hasattr(comp, 'vds_max'):
                    specs = []
                    if comp.vds_max:
                        specs.append(f"VDS(max): {comp.vds_max}V")
                    if hasattr(comp, 'id_continuous') and comp.id_continuous:
                        specs.append(f"ID(cont): {comp.id_continuous}A")
                    if hasattr(comp, 'id_pulsed') and comp.id_pulsed:
                        specs.append(f"ID(pulsed): {comp.id_pulsed}A")
                    if hasattr(comp, 'rds_on') and comp.rds_on:
                        if comp.rds_on < 1:
                            specs.append(f"RDS(on): {comp.rds_on*1000:.1f}mΩ")
                        else:
                            specs.append(f"RDS(on): {comp.rds_on:.3f}Ω")
                    if hasattr(comp, 'vgs_threshold') and comp.vgs_threshold:
                        specs.append(f"VGS(th): {comp.vgs_threshold}V")
                    if hasattr(comp, 'qg_total') and comp.qg_total:
                        specs.append(f"Qg: {comp.qg_total}nC")
                    if hasattr(comp, 'type') and comp.type:
                        specs.append(f"Tipo: {comp.type}")
                    if hasattr(comp, 'package') and comp.package and comp.package != "Unknown":
                        specs.append(f"Package: {comp.package}")
                    
                    if specs:
                        lines.append(f"   **Especificaciones:** {' | '.join(specs)}")
                
                # Diode specific specs
                elif hasattr(comp, 'vrrm'):
                    specs = []
                    if comp.vrrm:
                        specs.append(f"VRRM: {comp.vrrm}V")
                    if hasattr(comp, 'if_avg') and comp.if_avg:
                        specs.append(f"IF(avg): {comp.if_avg}A")
                    if hasattr(comp, 'vf') and comp.vf:
                        specs.append(f"VF: {comp.vf}V")
                    if hasattr(comp, 'trr') and comp.trr:
                        specs.append(f"trr: {comp.trr}ns")
                    if hasattr(comp, 'type') and comp.type and comp.type != "Schottky":
                        specs.append(f"Tipo: {comp.type}")
                    if hasattr(comp, 'package') and comp.package and comp.package != "Unknown":
                        specs.append(f"Package: {comp.package}")
                    
                    if specs:
                        lines.append(f"   **Especificaciones:** {' | '.join(specs)}")
                
                # Capacitor specific specs
                elif hasattr(comp, 'capacitance'):
                    specs = []
                    if comp.capacitance:
                        cap_uf = comp.capacitance * 1e6
                        if cap_uf >= 1000:
                            specs.append(f"C: {cap_uf/1000:.2f}mF")
                        elif cap_uf >= 1:
                            specs.append(f"C: {cap_uf:.1f}µF")
                        else:
                            cap_nf = comp.capacitance * 1e9
                            specs.append(f"C: {cap_nf:.1f}nF")
                    if hasattr(comp, 'voltage_rating') and comp.voltage_rating:
                        specs.append(f"V(rated): {comp.voltage_rating}V")
                    if hasattr(comp, 'tolerance') and comp.tolerance:
                        specs.append(f"Tol: ±{comp.tolerance}%")
                    if hasattr(comp, 'esr') and comp.esr:
                        if comp.esr < 1:
                            specs.append(f"ESR: {comp.esr*1000:.1f}mΩ")
                        else:
                            specs.append(f"ESR: {comp.esr:.2f}Ω")
                    if hasattr(comp, 'ripple_current') and comp.ripple_current:
                        specs.append(f"I(ripple): {comp.ripple_current}A")
                    if hasattr(comp, 'dielectric') and comp.dielectric and comp.dielectric != "Unknown":
                        specs.append(f"Dieléctrico: {comp.dielectric}")
                    if hasattr(comp, 'package') and comp.package and comp.package != "Unknown":
                        specs.append(f"Package: {comp.package}")
                    
                    if specs:
                        lines.append(f"   **Especificaciones:** {' | '.join(specs)}")
                
                # Inductor specific specs
                elif hasattr(comp, 'inductance'):
                    specs = []
                    if comp.inductance:
                        ind_uh = comp.inductance * 1e6
                        if ind_uh >= 1000:
                            specs.append(f"L: {ind_uh/1000:.2f}mH")
                        else:
                            specs.append(f"L: {ind_uh:.1f}µH")
                    if hasattr(comp, 'current_rating') and comp.current_rating:
                        specs.append(f"I(rated): {comp.current_rating}A")
                    if hasattr(comp, 'saturation_current') and comp.saturation_current:
                        specs.append(f"I(sat): {comp.saturation_current}A")
                    if hasattr(comp, 'dcr') and comp.dcr:
                        if comp.dcr < 1:
                            specs.append(f"DCR: {comp.dcr*1000:.1f}mΩ")
                        else:
                            specs.append(f"DCR: {comp.dcr:.3f}Ω")
                    if hasattr(comp, 'core_material') and comp.core_material:
                        specs.append(f"Núcleo: {comp.core_material}")
                    if hasattr(comp, 'package') and comp.package and comp.package != "Unknown":
                        specs.append(f"Package: {comp.package}")
                    
                    if specs:
                        lines.append(f"   **Especificaciones:** {' | '.join(specs)}")
                
                # Add links
                links = []
                if hasattr(comp, 'product_url') and comp.product_url:
                    links.append(f"[Ver en Mouser]({comp.product_url})")
                if hasattr(comp, 'datasheet_url') and comp.datasheet_url:
                    links.append(f"[Datasheet]({comp.datasheet_url})")
                
                if links:
                    lines.append(f"   {' | '.join(links)}")
                
                lines.append("")  # Empty line between components
        
        return "\n".join(lines)


@dataclass
class WorkflowContainer:
    factory: ConverterFactory
    validator: ValidationEngine
    workflow: DesignWorkflowService


def _build_workflow() -> WorkflowContainer:
    factory = ConverterFactory()
    register_default_designers(factory)

    validator = ValidationEngine()
    register_default_rules(validator)

    workflow = DesignWorkflowService(factory=factory, validation_engine=validator)
    # Attach factory on workflow for easier access from the UI
    workflow.factory = factory  # type: ignore[attr-defined]
    return WorkflowContainer(factory=factory, validator=validator, workflow=workflow)


def run_app() -> None:
    app = DesignWizardApp()
    app.run()


APP = "tutor_virtual.presentation.app:DesignWizardApp"


if __name__ == "__main__":
    run_app()
