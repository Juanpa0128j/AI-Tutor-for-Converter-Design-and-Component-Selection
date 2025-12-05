"""Gradio-based web interface for the AI Power Converter Designer."""

import gradio as gr
import pandas as pd
from typing import List
from .gradio_adapter import GradioAdapter
from .spec_schema import FORMS, FieldDefinition

# Initialize adapter
adapter = GradioAdapter()

def create_app():
    # Get available topologies
    topologies = adapter.get_available_topologies() # List of (Name, ID)
    topology_choices = [t[0] for t in topologies]
    
    # Get all possible field keys to create widgets
    all_field_keys = adapter.get_all_field_keys()
    
    # Helper to get field metadata
    def get_field_meta(key: str) -> FieldDefinition:
        for form in FORMS.values():
            for f in list(form.fields) + list(form.constraint_fields):
                if f.key == key:
                    return f
        return FieldDefinition(key, key, "", "")

    with gr.Blocks(title="AI Power Converter Designer") as demo:
        demo.theme = gr.themes.Soft()
        gr.Markdown("# ⚡ AI Tutor: Diseñador de Convertidores de Potencia")
        gr.Markdown("Seleccione una topología, ingrese los parámetros y obtenga un prediseño con componentes recomendados.")
        
        with gr.Row():
            # --- Left Column: Controls ---
            with gr.Column(scale=1, min_width=300):
                gr.Markdown("### 1. Configuración")
                
                # Topology Selector
                topology_dropdown = gr.Dropdown(
                    choices=topology_choices,
                    value=topology_choices[0] if topology_choices else None,
                    label="Topología",
                    type="value",
                    interactive=True
                )
                
                # Dynamic Inputs Container
                gr.Markdown("### 2. Parámetros Operativos")
                input_widgets = {}
                input_containers = {}
                
                # Create all widgets but hide them initially
                # We sort them to try to keep related ones together if possible, 
                # but simple creation order is fine for now.
                for key in all_field_keys:
                    meta = get_field_meta(key)
                    label = f"{meta.label} ({meta.unit})" if meta.unit else meta.label
                    
                    # Determine initial value from placeholder if possible
                    initial_val = 0
                    if meta.default is not None:
                        initial_val = meta.default
                    elif meta.placeholder:
                        try:
                            initial_val = float(meta.placeholder)
                        except:
                            pass

                    # Wrap in a Column to control visibility more reliably
                    with gr.Column(visible=False) as container:
                        # Use Number for float inputs
                        input_widgets[key] = gr.Number(
                            label=label,
                            value=initial_val,
                            interactive=True
                        )
                    input_containers[key] = container
                
                # Prioritization Weights
                gr.Markdown("### 3. Priorización de Componentes")
                with gr.Group():
                    w_cost = gr.Slider(0, 1, value=0.3, step=0.05, label="Costo")
                    w_avail = gr.Slider(0, 1, value=0.25, step=0.05, label="Disponibilidad")
                    w_eff = gr.Slider(0, 1, value=0.25, step=0.05, label="Eficiencia")
                    w_therm = gr.Slider(0, 1, value=0.2, step=0.05, label="Térmica")
                
                btn_calc = gr.Button("🚀 Calcular Diseño", variant="primary", size="lg")

            # --- Right Column: Results ---
            with gr.Column(scale=2, visible=True) as results_container:
                gr.Markdown("### 📊 Reporte de Diseño")
                result_md = gr.Markdown(
                    value="Seleccione una topología y presione Calcular para ver los resultados.",
                    elem_classes=["markdown-body"]
                )
                
                gr.Markdown("### 🔌 Catálogo de Componentes")
                components_df = gr.Dataframe(
                    headers=["Tipo", "Fabricante", "Número de Parte", "Descripción", "Precio (USD)", "Stock", "Score", "Datasheet", "Link"],
                    datatype=["str", "str", "str", "str", "number", "number", "str", "html", "html"],
                    interactive=False,
                    wrap=True
                )

        # --- Event Handlers ---

        def update_ui(topo_name):
            """Updates visibility and default values of input fields based on selected topology."""
            print(f"DEBUG: update_ui called with '{topo_name}'")
            if not topo_name:
                # Hide all containers and don't change values
                col_updates = [gr.Column(visible=False)] * len(all_field_keys)
                num_updates = [gr.Number()] * len(all_field_keys)
                return col_updates + num_updates
            
            # Find ID from name
            topo_id = None
            for name, tid in topologies:
                if name == topo_name:
                    topo_id = tid
                    break
            
            print(f"DEBUG: Found topo_id: {topo_id}")
            
            if not topo_id:
                col_updates = [gr.Column(visible=False)] * len(all_field_keys)
                num_updates = [gr.Number()] * len(all_field_keys)
                return col_updates + num_updates
            
            # Get active fields and defaults for this topology
            active_keys = set(adapter.get_topology_fields(topo_id))
            defaults = adapter.get_topology_defaults(topo_id)
            
            col_updates = []
            num_updates = []
            
            for key in all_field_keys:
                is_visible = key in active_keys
                col_updates.append(gr.Column(visible=is_visible))
                
                # Update value if key is active and has a default
                if is_visible and key in defaults:
                    num_updates.append(gr.Number(value=defaults[key]))
                else:
                    # If not visible or no default, keep current value (pass no update)
                    # Or set to 0/None? Textual app resets to default or empty.
                    # Let's set to default if available, else 0 if visible, else ignore
                    if is_visible:
                        num_updates.append(gr.Number(value=0))
                    else:
                        num_updates.append(gr.Number()) # No change
            
            return col_updates + num_updates

        async def run_calculation(topo_name, w_c, w_a, w_e, w_t, *field_values):
            """Collects inputs and runs the design workflow."""
            print(f"DEBUG: run_calculation called for {topo_name}")
            if not topo_name:
                return "⚠️ Por favor seleccione una topología.", pd.DataFrame()
            
            # Find ID from name
            topo_id = None
            for name, tid in topologies:
                if name == topo_name:
                    topo_id = tid
                    break

            if not topo_id:
                return "⚠️ Topología inválida.", pd.DataFrame()
            
            # Map list of values back to keys
            inputs_dict = {}
            for key, val in zip(all_field_keys, field_values):
                if val is not None:
                    inputs_dict[key] = val
            
            weights = {
                "cost": w_c, 
                "availability": w_a, 
                "efficiency": w_e, 
                "thermal": w_t
            }
            
            print(f"DEBUG: Calling adapter.run_design with inputs: {inputs_dict}")
            # Run adapter logic
            report, df = await adapter.run_design(topo_id, inputs_dict, weights)
            print(f"DEBUG: Design finished. Report length: {len(report)}, DF shape: {df.shape}")
            
            return report, df

        # Wiring
        input_widget_list = list(input_widgets.values())
        input_container_list = list(input_containers.values())
        
        topology_dropdown.change(
            fn=update_ui,
            inputs=[topology_dropdown],
            outputs=input_container_list + input_widget_list
        )
        
        btn_calc.click(
            fn=run_calculation,
            inputs=[topology_dropdown, w_cost, w_avail, w_eff, w_therm] + input_widget_list,
            outputs=[result_md, components_df]
        )
        
        # Initial load
        demo.load(
            fn=update_ui,
            inputs=[topology_dropdown],
            outputs=input_container_list + input_widget_list
        )

    return demo

if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860)
