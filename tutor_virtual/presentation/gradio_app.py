"""Gradio-based web interface for the AI Power Converter Designer."""

import logging
import gradio as gr
import pandas as pd
from typing import List
from .gradio_adapter import GradioAdapter
from .spec_schema import FORMS, FieldDefinition

logger = logging.getLogger(__name__)

# Initialize adapter
adapter = GradioAdapter()

def create_app():
    # Get available topologies
    topologies = adapter.get_available_topologies() # List of (Key, ID)
    
    # Get all possible field keys to create widgets
    all_field_keys = adapter.get_all_field_keys()
    
    # Helper to get field metadata
    def get_field_meta(key: str) -> FieldDefinition:
        for form in FORMS.values():
            for f in list(form.fields) + list(form.constraint_fields):
                if f.key == key:
                    return f
        return FieldDefinition(key, key, "", "")

    # Initialize Tutor Service
    from tutor_virtual.application.tutor_service import TutorService
    try:
        tutor_service = TutorService()
        logger.info("Tutor Service initialized successfully")
    except Exception as e:
        logger.error(f"Tutor Service failed to initialize: {e}")
        tutor_service = None

    # Initialize I18n helpers
    from .translations import get_text, LANG_MAP

    # Initial Topology Choices (Español default)
    def get_topology_choices(lang_label="Español"):
        return [(get_text(t[0], lang_label), t[1]) for t in topologies]

    initial_choices = get_topology_choices()

    import uuid
    
    async def chat_response(message, history, session_id):
        if not tutor_service:
            return "⚠️ Service unavailable."
        return await tutor_service.ask_question(message, session_id=session_id)

    with gr.Blocks(title="AI Power Converter Designer") as demo:
        demo.theme = gr.themes.Soft()
        
        # State for language
        lang_state = gr.State(value="Español")
        chat_history = gr.State(value=[])
        
        # Header with Language Selector
        with gr.Row():
            with gr.Column(scale=4):
                header_md = gr.Markdown(get_text("main_header", "Español"))
            with gr.Column(scale=1):
                lang_dropdown = gr.Dropdown(
                    choices=list(LANG_MAP.keys()),
                    value="Español",
                    label="Language / Idioma",
                    interactive=True,
                    show_label=True
                )

        with gr.Tabs() as tabs:
            # --- Designer Tab ---
            with gr.TabItem(get_text("tab_designer", "Español")) as tab_designer:
                designer_intro_md = gr.Markdown(get_text("designer_intro", "Español"))
                
                with gr.Row():
                    # --- Left Column: Controls ---
                    with gr.Column(scale=1, min_width=300):
                        config_header_md = gr.Markdown(get_text("config_header", "Español"))
                        
                        # Topology Selector
                        topology_dropdown = gr.Dropdown(
                            choices=initial_choices,
                            value=initial_choices[0][1] if initial_choices else None,
                            label=get_text("topology_label", "Español"),
                            type="value",
                            interactive=True
                        )
                        
                        # Dynamic Inputs Container
                        params_header_md = gr.Markdown(get_text("params_header", "Español"))
                        input_widgets = {}
                        
                        # Determine initial active keys and defaults
                        initial_topo_id = initial_choices[0][1] if initial_choices else None
                        initial_active_keys = set()
                        initial_defaults = {}
                        
                        if initial_topo_id:
                            initial_active_keys = set(adapter.get_topology_fields(initial_topo_id))
                            initial_defaults = adapter.get_topology_defaults(initial_topo_id)

                        # Create all widgets
                        for key in all_field_keys:
                            meta = get_field_meta(key)
                            label_text = get_text(meta.label, "Español")
                            label = f"{label_text} ({meta.unit})" if meta.unit else label_text
                            
                            # Determine initial value and visibility
                            is_visible = key in initial_active_keys
                            val = initial_defaults.get(key, 0) if is_visible else 0
                            
                            input_widgets[key] = gr.Number(
                                label=label,
                                value=val,
                                interactive=True,
                                visible=is_visible
                            )
                        
                        # Prioritization Weights
                        weights_header_md = gr.Markdown(get_text("weights_header", "Español"))
                        with gr.Group():
                            w_cost = gr.Slider(0, 1, value=0.3, step=0.05, label=get_text("weight_cost", "Español"))
                            w_avail = gr.Slider(0, 1, value=0.25, step=0.05, label=get_text("weight_availability", "Español"))
                            w_eff = gr.Slider(0, 1, value=0.25, step=0.05, label=get_text("weight_efficiency", "Español"))
                            w_therm = gr.Slider(0, 1, value=0.2, step=0.05, label=get_text("weight_thermal", "Español"))
                        
                        btn_calc = gr.Button(get_text("calc_button", "Español"), variant="primary", size="lg")

                    # --- Right Column: Results ---
                    with gr.Column(scale=2):
                        report_header_md = gr.Markdown(get_text("report_header", "Español"))
                        result_md = gr.Markdown(
                            value=get_text("report_placeholder", "Español"),
                            elem_classes=["markdown-body"]
                        )
                        
                        catalog_header_md = gr.Markdown(get_text("catalog_header", "Español"))
                        components_df = gr.Dataframe(
                            headers=[
                                get_text("col_type", "Español"), get_text("col_mfr", "Español"), 
                                get_text("col_part", "Español"), get_text("col_desc", "Español"), 
                                get_text("col_price", "Español"), get_text("col_stock", "Español"), 
                                get_text("col_score", "Español"), get_text("col_datasheet", "Español"), 
                                get_text("col_link", "Español")
                            ],
                            datatype=["str", "str", "str", "str", "number", "number", "str", "html", "html"],
                            interactive=False,
                            wrap=True
                        )

            # --- Tutor Tab ---
            with gr.TabItem(get_text("tab_tutor", "Español")) as tab_tutor:
                tutor_header_md = gr.Markdown(get_text("tutor_header", "Español"))
                tutor_intro_md = gr.Markdown(get_text("tutor_intro", "Español"))
                
                chatbot = gr.Chatbot(
                    label=get_text("tab_tutor", "Español"),
                    value=chat_history.value, # Load history
                    latex_delimiters=[
                        {"left": "$$", "right": "$$", "display": True},
                        {"left": "$", "right": "$", "display": False},
                        {"left": "\\(", "right": "\\)", "display": False},
                        {"left": "\\[", "right": "\\]", "display": True},
                    ],
                    height=500
                )
                
                with gr.Row():
                    msg = gr.Textbox(
                        show_label=False,
                        placeholder="Type your message...",
                        scale=4,
                        container=False
                    )
                    submit_btn = gr.Button("Send", scale=1, variant="primary")
                
                clear_btn = gr.ClearButton([msg, chatbot], value="Clear Chat")
                
                # Examples using Dataset for dynamic updates
                examples_data = [
                    [get_text("ex_buck", "Español")],
                    [get_text("ex_inductor", "Español")],
                    [get_text("ex_diff", "Español")],
                    [get_text("ex_freq", "Español")]
                ]
                
                examples_dataset = gr.Dataset(
                    label="Examples",
                    components=[msg],
                    samples=examples_data,
                    type="values"
                )

            # --- Documents Tab ---
            with gr.TabItem(get_text("tab_documents", "Español")) as tab_documents:
                docs_header_md = gr.Markdown(get_text("docs_header", "Español"))
                docs_intro_md = gr.Markdown(get_text("docs_intro", "Español"))
                
                with gr.Row():
                    with gr.Column(scale=1):
                        # Strategy selector
                        strategy_radio = gr.Radio(
                            choices=["fast", "hi_res", "auto", "ocr_only"],
                            value="fast",
                            label="Strategy / Estrategia",
                            info="fast: Text only (fastest). hi_res: OCR/Tables (slow). auto: Automatic."
                        )
                        
                        # File upload
                        file_upload = gr.File(
                            label=get_text("docs_upload_label", "Español"),
                            file_types=[".pdf", ".docx", ".doc", ".txt", ".md", ".rst", 
                                       ".xlsx", ".xls", ".csv", ".pptx", ".ppt", 
                                       ".html", ".htm", ".xml", ".epub", ".odt"],
                            file_count="multiple"
                        )
                        upload_status = gr.Markdown("")
                    
                    with gr.Column(scale=2):
                        docs_list_header_md = gr.Markdown(get_text("docs_list_header", "Español"))
                        docs_list = gr.Dataframe(
                            headers=[
                                get_text("docs_col_id", "Español"),
                                get_text("docs_col_filename", "Español"),
                                get_text("docs_col_chunks", "Español"),
                                get_text("docs_col_indexed", "Español")
                            ],
                            datatype=["str", "str", "number", "str"],
                            interactive=False,
                            wrap=True,
                            value=[]
                        )
                        refresh_docs_btn = gr.Button(get_text("docs_refresh_btn", "Español"), size="sm")
                        
                        # Delete controls
                        with gr.Row():
                            with gr.Column(scale=3):
                                delete_dropdown = gr.Dropdown(
                                    label="Select Document to Delete / Seleccionar Documento a Borrar",
                                    choices=[],
                                    interactive=True
                                )
                            with gr.Column(scale=1):
                                delete_btn = gr.Button("Delete / Borrar", variant="stop")

        # --- Logic ---

        # 1. Update Language
        def update_language(lang_label):
            new_examples = [
                [get_text("ex_buck", lang_label)],
                [get_text("ex_inductor", lang_label)],
                [get_text("ex_diff", lang_label)],
                [get_text("ex_freq", lang_label)]
            ]
            
            # Update Topology Choices
            new_topo_choices = get_topology_choices(lang_label)
            
            updates = [
                gr.update(value=get_text("main_header", lang_label)),
                gr.update(label=get_text("tab_designer", lang_label)),
                gr.update(value=get_text("designer_intro", lang_label)),
                gr.update(value=get_text("config_header", lang_label)),
                gr.update(label=get_text("topology_label", lang_label), choices=new_topo_choices),
                gr.update(value=get_text("params_header", lang_label)),
                gr.update(value=get_text("weights_header", lang_label)),
                gr.update(label=get_text("weight_cost", lang_label)),
                gr.update(label=get_text("weight_availability", lang_label)),
                gr.update(label=get_text("weight_efficiency", lang_label)),
                gr.update(label=get_text("weight_thermal", lang_label)),
                gr.update(value=get_text("calc_button", lang_label)),
                gr.update(value=get_text("report_header", lang_label)),
                gr.update(value=get_text("report_placeholder", lang_label)), # Reset placeholder? Maybe not if result exists.
                gr.update(value=get_text("catalog_header", lang_label)),
                gr.update(headers=[
                    get_text("col_type", lang_label), get_text("col_mfr", lang_label), 
                    get_text("col_part", lang_label), get_text("col_desc", lang_label), 
                    get_text("col_price", lang_label), get_text("col_stock", lang_label), 
                    get_text("col_score", lang_label), get_text("col_datasheet", lang_label), 
                    get_text("col_link", lang_label)
                ], value=None), # Force refresh with new headers
                gr.update(label=get_text("tab_tutor", lang_label)),
                gr.update(value=get_text("tutor_header", lang_label)),
                gr.update(value=get_text("tutor_intro", lang_label)),
                gr.update(label=get_text("tab_tutor", lang_label)),
                gr.update(samples=new_examples),
                # Documents tab
                gr.update(label=get_text("tab_documents", lang_label)),
                gr.update(value=get_text("docs_header", lang_label)),
                gr.update(value=get_text("docs_intro", lang_label)),
                gr.update(label=get_text("docs_upload_label", lang_label)),
                gr.update(value=get_text("docs_list_header", lang_label)),
                gr.update(headers=[
                    get_text("docs_col_id", lang_label),
                    get_text("docs_col_filename", lang_label),
                    get_text("docs_col_chunks", lang_label),
                    get_text("docs_col_indexed", lang_label)
                ], value=None),  # Force refresh with new headers
                gr.update(value=get_text("docs_refresh_btn", lang_label)),
                gr.update(label=get_text("docs_delete_label", lang_label)),
                gr.update(value=get_text("docs_delete_btn", lang_label)),
            ]
            
            # Update Input Widget Labels
            for key in all_field_keys:
                meta = get_field_meta(key)
                label_text = get_text(meta.label, lang_label)
                label = f"{label_text} ({meta.unit})" if meta.unit else label_text
                updates.append(gr.update(label=label))
                
            return updates

        # List of components to update
        lang_outputs = [
            header_md, tab_designer, designer_intro_md, config_header_md, topology_dropdown,
            params_header_md, weights_header_md, w_cost, w_avail, w_eff, w_therm,
            btn_calc, report_header_md, result_md, catalog_header_md, components_df,
            tab_tutor, tutor_header_md, tutor_intro_md, chatbot, examples_dataset,
            # Documents tab
            tab_documents, docs_header_md, docs_intro_md, file_upload, docs_list_header_md,
            docs_list, refresh_docs_btn, delete_dropdown, delete_btn
        ] + [input_widgets[key] for key in all_field_keys]
        
        lang_dropdown.change(
            fn=update_language,
            inputs=[lang_dropdown],
            outputs=lang_outputs
        )
        
        # Handle example click
        def load_example(example):
            return example[0]
            
        examples_dataset.click(
            fn=load_example,
            inputs=[examples_dataset],
            outputs=[msg]
        )

        # 2. Update UI Visibility (Topology)
        def update_ui_visibility(topo_id_val, lang_label):
            if not topo_id_val:
                return [gr.update(visible=False)] * len(all_field_keys)
            
            # topo_id_val is already the ID because Dropdown type="value"
            active_keys = set(adapter.get_topology_fields(topo_id_val))
            defaults = adapter.get_topology_defaults(topo_id_val)
            
            updates = []
            for key in all_field_keys:
                is_visible = key in active_keys
                val = defaults.get(key, 0) if is_visible else 0
                
                # Update label based on current language
                meta = get_field_meta(key)
                label_text = get_text(meta.label, lang_label)
                label = f"{label_text} ({meta.unit})" if meta.unit else label_text
                
                updates.append(gr.update(visible=is_visible, value=val, label=label))
            return updates

        input_widget_list = [input_widgets[key] for key in all_field_keys]
        
        topology_dropdown.change(
            fn=update_ui_visibility,
            inputs=[topology_dropdown, lang_dropdown],
            outputs=input_widget_list
        )

        # 3. Calculation
        # State for design context
        design_state = gr.State(value=None)

        async def run_calc_wrapper(topo_id_val, wc, wa, we, wt, lang_label, *values):
            # Wrapper to handle i18n messages
            if not topo_id_val:
                return get_text("msg_select_topo", lang_label), pd.DataFrame(), None
            
            inputs_dict = {k: v for k, v in zip(all_field_keys, values) if v is not None}
            weights = {"cost": wc, "availability": wa, "efficiency": we, "thermal": wt}
            
            return await adapter.run_design(topo_id_val, inputs_dict, weights, lang_label)

        btn_calc.click(
            fn=run_calc_wrapper,
            inputs=[topology_dropdown, w_cost, w_avail, w_eff, w_therm, lang_dropdown] + input_widget_list,
            outputs=[result_md, components_df, design_state]
        )

        # Session ID State
        session_id_state = gr.State(lambda: str(uuid.uuid4()))

        # Listener to update tutor context
        async def sync_design_to_tutor(design_data, session_id, lang_label):
            if design_data and tutor_service:
                await tutor_service.update_context(session_id, design_data)
                gr.Info(get_text("msg_tutor_context_updated", lang_label))
            return None

        design_state.change(
            fn=sync_design_to_tutor,
            inputs=[design_state, session_id_state, lang_dropdown],
            outputs=[]
        )

        # 4. Chat Logic (with token streaming)
        async def respond(message, history, session_id):
            if not message:
                yield "", history
                return
            
            if not tutor_service:
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": "⚠️ Service unavailable."})
                yield "", history
                return
            
            # Add user message
            history.append({"role": "user", "content": message})
            yield "", history
            
            # Stream response token by token
            partial_message = ""
            async for token in tutor_service.ask_question_stream(message, session_id):
                partial_message += token
                # Update history with partial response
                history_with_streaming = history + [{"role": "assistant", "content": partial_message}]
                yield "", history_with_streaming
            
            # Finalize with complete message in history
            history.append({"role": "assistant", "content": partial_message})
            yield "", history

        msg.submit(respond, [msg, chatbot, session_id_state], [msg, chatbot])
        submit_btn.click(respond, [msg, chatbot, session_id_state], [msg, chatbot])
        
        # Sync history state
        chatbot.change(lambda x: x, chatbot, chat_history)

        # 5. Document Upload & Management Logic
        def get_documents_data():
            """Get raw list of indexed documents."""
            try:
                from tutor_virtual.infrastructure.rag import get_rag_service
                rag_service = get_rag_service()
                return rag_service.get_indexed_documents()
            except Exception as e:
                logger.error(f"Error getting documents list: {e}")
                return []

        def refresh_all_docs_ui():
            """Refresh both the dataframe and the delete dropdown."""
            docs = get_documents_data()
            
            # Format for Dataframe
            df_data = []
            if docs:
                df_data = [[d["doc_id"][:8], d["filename"], d["chunk_count"], d["indexed_at"][:19]] for d in docs]
            
            # Format for Dropdown
            dropdown_choices = []
            if docs:
                dropdown_choices = [f"{d['filename']} ({d['doc_id']})" for d in docs]
            
            return df_data, gr.update(choices=dropdown_choices)

        # State for tracking background jobs
        active_jobs = gr.State([])

        def upload_document(files, strategy, lang_label, current_jobs):
            """Handle document upload via background job."""
            if not files:
                df_data, _ = refresh_all_docs_ui()
                return get_text("docs_no_documents", lang_label), df_data, current_jobs
            
            if not isinstance(files, list):
                files = [files]

            try:
                job_ids = []
                for file in files:
                    orig_name = file.orig_name if hasattr(file, 'orig_name') else None
                    job_id = adapter.submit_indexing_job(file.name, orig_name, strategy)
                    job_ids.append(job_id)
                
                msg = get_text("docs_upload_started", lang_label).format(count=len(job_ids), strategy=strategy)
                gr.Info(msg)
                
                df_data, _ = refresh_all_docs_ui()
                updated_jobs = current_jobs + job_ids
                return msg, df_data, updated_jobs
                
            except Exception as e:
                logger.error(f"Error submitting jobs: {e}")
                err_msg = f"Error: {str(e)}"
                gr.Error(err_msg)
                df_data, _ = refresh_all_docs_ui()
                return err_msg, df_data, current_jobs
        
        def poll_jobs(current_jobs, lang_label):
            """Check status of active jobs and notify user."""
            if not current_jobs:
                return current_jobs
            
            remaining_jobs = []
            for job_id in current_jobs:
                status_data = adapter.get_job_status(job_id)
                status = status_data.get("status")
                
                if status == "completed":
                    # Job finished successfully
                    filename = status_data.get("result", {}).get("filename", "Document")
                    gr.Info(get_text("docs_job_completed", lang_label).format(filename=filename))
                    # Don't add to remaining_jobs
                elif status == "failed":
                    # Job failed
                    error = status_data.get("error", "Unknown error")
                    gr.Error(get_text("docs_job_failed", lang_label).format(error=error))
                    # Don't add to remaining_jobs
                else:
                    # Still running (queued, processing)
                    remaining_jobs.append(job_id)
            
            return remaining_jobs

        def handle_delete(selection, lang_label):
            """Handle document deletion."""
            if not selection:
                return get_text("docs_select_none", lang_label), *refresh_all_docs_ui()
            
            try:
                # Extract ID from "Filename (ID)" format
                doc_id = selection.split("(")[-1].strip(")")
                
                success = adapter.delete_document(doc_id)
                
                if success:
                    msg = get_text("docs_delete_success", lang_label).format(doc_id=doc_id)
                    gr.Info(msg)
                else:
                    msg = get_text("docs_delete_error", lang_label).format(doc_id=doc_id)
                    gr.Error(msg)
                
                return msg, *refresh_all_docs_ui()
                
            except Exception as e:
                logger.error(f"Error deleting document: {e}")
                return f"Error: {str(e)}", *refresh_all_docs_ui()

        # Timer to auto-refresh document list every 10 seconds
        refresh_timer = gr.Timer(10)
        refresh_timer.tick(
            fn=poll_jobs,
            inputs=[active_jobs, lang_dropdown],
            outputs=[active_jobs]
        ).then(
            fn=refresh_all_docs_ui,
            outputs=[docs_list, delete_dropdown]
        )
        
        file_upload.change(
            fn=upload_document,
            inputs=[file_upload, strategy_radio, lang_dropdown, active_jobs],
            outputs=[upload_status, docs_list, active_jobs]
        )
        
        refresh_docs_btn.click(
            fn=refresh_all_docs_ui,
            inputs=[],
            outputs=[docs_list, delete_dropdown]
        )
        
        delete_btn.click(
            fn=handle_delete,
            inputs=[delete_dropdown, lang_dropdown],
            outputs=[upload_status, docs_list, delete_dropdown]
        )
        
        # Initialize documents list on load
        demo.load(fn=refresh_all_docs_ui, inputs=[], outputs=[docs_list, delete_dropdown])

    return demo, None

if __name__ == "__main__":
    app, i18n = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860, i18n=i18n)
