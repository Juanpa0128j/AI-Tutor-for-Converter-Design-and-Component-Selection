"""Textual-based wizard to interact with the design workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Label, Markdown, Select

from tutor_virtual.application.services.design_workflow import DesignWorkflowService, ValidationFailedError
from tutor_virtual.domain.converters import ConverterFactory, TopologyId, register_default_designers
from tutor_virtual.domain.validation import ValidationEngine, register_default_rules
from tutor_virtual.shared.dto import ConverterSpec, DesignContext, DesignRequest

from .spec_schema import FieldDefinition, TopologyForm, available_forms


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
        margin: 0 2;
        min-height: 1;
        width: auto;
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield self._build_topology_panel()
            yield self._build_form_panel()
        yield Footer()

    def _build_topology_panel(self) -> Container:
        options = [(form.title, form.topology_id.value) for form in self._forms]
        select = Select(options=options, prompt="Seleccione topología", id="topology-select")
        return Container(
            Label("Topologías disponibles", classes="title"),
            select,
            Markdown("Utilice las flechas para navegar y Enter para confirmar."),
            id="topology-pane",
        )

    def _build_form_panel(self) -> Container:
        self._form_scroll = VerticalScroll(id="form-scroll")
        self._status = Markdown("Seleccione una topología para comenzar.", id="results")
        buttons = Horizontal(
            Button("Calcular", id="run-button", variant="success"),
            Button("Limpiar", id="clear-button", variant="primary"),
            id="form-buttons",
        )
        return Container(
            Label("Especificaciones", classes="title", id="form-title"),
            self._form_scroll,
            self._status,
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

    async def _handle_clear(self) -> None:
        if not self._current_form:
            return
        for field_state in list(self._current_form.fields.values()) + list(self._current_form.constraint_fields.values()):
            field_state.widget.value = str(field_state.definition.default or "")
        self._status.update("Campos reiniciados. Modifique valores y ejecute nuevamente.")


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
