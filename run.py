#!/usr/bin/env python
"""Script de entrada para ejecutar la aplicación del tutor virtual."""

import sys

if __name__ == "__main__":
    # Check for legacy flag if we want to keep TUI available
    if "--tui" in sys.argv:
        from tutor_virtual.presentation.app import run_app
        run_app()
    else:
        from tutor_virtual.presentation.gradio_app import create_app
        print("🚀 Iniciando interfaz web en http://localhost:7860")
        app, _ = create_app()
        app.launch(server_name="0.0.0.0", server_port=7860, share=False)
