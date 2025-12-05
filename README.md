# 🎓 Tutor Virtual para Diseño de Convertidores de Potencia

Sistema inteligente de asistencia para el prediseño y selección de componentes en convertidores de electrónica de potencia.

## 📋 Descripción del Proyecto

Este proyecto implementa un tutor virtual que guía a estudiantes e ingenieros en el diseño preliminar de convertidores de electrónica de potencia. El sistema proporciona:

- ✅ Cálculos automatizados de prediseño para 13 topologías diferentes
- ✅ Validación de especificaciones según normas IEEE/IEC
- ✅ Estimación de pérdidas en componentes
- ✅ Interfaz de usuario en terminal con Gradio (Textual opcional)
- ✅ Recomendaciones de componentes comerciales
- ✅ Modo chatbot con IA para asistencia interactiva
- ✅ Interfaz web (Gradio) con TUI opcional (Textual)
- ✅ Recomendaciones de componentes comerciales (integración Mouser experimental)
- ✅ Modo chatbot con IA para asistencia interactiva (streaming de respuestas, RAG)

## 🏗️ Arquitectura

El proyecto sigue una arquitectura hexagonal (ports & adapters) con Domain-Driven Design:

```
tutor_virtual/
├── domain/              # Lógica de negocio y reglas de dominio
│   ├── converters/      # 13 diseñadores de topologías concretas
│   ├── validation/      # Motor de validación y reglas por topología
│   └── ports/           # Interfaces y contratos
├── application/         # Casos de uso y servicios de aplicación
│   └── services/        # DesignWorkflowService (orquestación)
├── infrastructure/      # Adaptadores externos y servicios
│   ├── catalogs/        # Adaptadores de catálogos (Mouser, cache Redis)
│   ├── rag/             # Document processing, vector store y RAG service
│   └── ai_agent.py      # Agente LangChain y herramientas (prototipo)
├── presentation/        # Interfaz de usuario
│   ├── app.py           # TUI (Textual)
│   ├── gradio_app.py    # UI web (Gradio, experimental)
│   └── spec_schema.py   # Definición de formularios por topología
└── shared/              # DTOs y objetos compartidos
```

## ✨ Funcionalidades Implementadas

### 1. **Topologías Soportadas** (13 total)

#### AC-DC (Rectificadores)
- ✅ Rectificador monofásico de media onda
- ✅ Rectificador puente monofásico completo
- ✅ Rectificador trifásico

#### AC-AC (Control de Fase)
- ✅ Regulador con TRIAC

#### DC-DC (Conmutados)
- ✅ Buck (reductor)
- ✅ Boost (elevador)
- ✅ Buck-Boost (polaridad invertida)
- ✅ Ćuk
- ✅ Flyback (aislado)

#### DC-AC (Inversores)
- ✅ Inversor medio puente
- ✅ Inversor puente completo monofásico
- ✅ Inversor trifásico
- ✅ Modulación PWM (SPWM/SVPWM)

### 2. **Motor de Validación**
- ✅ Validación de rangos de duty cycle
- ✅ Verificación de relaciones de voltaje
- ✅ Límites de rizo de corriente y voltaje
- ✅ Validación de márgenes de seguridad
- ✅ Sistema de severidad (bloqueante/advertencia/informativo)

### 3. **Cálculos de Prediseño**
- ✅ Valores promedio y RMS de voltaje/corriente
- ✅ Dimensionamiento de inductores y capacitores
- ✅ Voltajes pico inverso (PIV) para semiconductores
- ✅ Estimación de pérdidas por conducción
- ✅ Cálculos de duty cycle y relación de transformación

### 4. **Interfaz de Usuario (TUI)**
- ✅ Selector de topologías con navegación por teclado
- ✅ Formularios dinámicos según topología seleccionada
- ✅ **Unidades mostradas para cada variable de entrada**
- ✅ **Resultados con formato Markdown estético**
- ✅ **Conversión automática de unidades** (µF, mH, kHz, etc.)
- ✅ Atajos de teclado (Ctrl+S para calcular, Escape/Q para salir)
- ✅ Validación en tiempo real con mensajes claros

### 5. **Integraciones e Infraestructura (recientes)**
- ✅ Integración básica con catálogos comerciales (Mouser) y servicio de recomendación de componentes (experimental)
- ✅ RAG (ingestión y búsqueda por similaridad) para documentos y primer flujo de indexado
- ✅ Agente AI basado en LangChain (prototipo) y conjunto de herramientas para diseño, búsqueda y simulación
- ✅ Servicio de simulación (tiempo-dominio) para Buck/Boost y herramientas de análisis
- ✅ Internacionalización (i18n) para UI (ES/EN) y refactor de formularios para usar claves de traducción
- ✅ Interfaz web mínima con Gradio (experimental) — UI complementaria a la TUI

## 🚧 Próximas Funcionalidades

### Corto Plazo
- [ ] Exportación de resultados (PDF, JSON, CSV)
- [ ] Historial de diseños guardados (persistencia SQLite)

### Mediano Plazo
- [ ] Modo chatbot con LLM (OpenAI/Anthropic) usando LangChain y RAG para:
  - Explicaciones paso a paso de los cálculos
  - Sugerencias de mejora de diseño
  - Respuestas a preguntas sobre conceptos
- [ ] Análisis de sensibilidad paramétrica
- [ ] Generación de diagramas esquemáticos
- [ ] Cálculo térmico de disipadores

## 🚀 Instalación y Ejecución

### Requisitos Previos
- Python 3.11 o superior
- Conda (recomendado) o venv

### Instalación

1. **Clonar el repositorio**
```bash
git clone https://github.com/Juanpa0128j/AI-Tutor-for-Converter-Design-and-Component-Selection.git
cd AI-Tutor-for-Converter-Design-and-Component-Selection
```

2. **Crear entorno virtual con Conda** (recomendado)
```bash
conda create -n tutor-virtual python=3.11
conda activate tutor-virtual
```

O con venv:
```bash
python -m venv venv
source venv/bin/activate  # En Linux/Mac
# venv\Scripts\activate   # En Windows
```

3. **Instalar dependencias**
```bash
pip install -e .
```

O instalar manualmente:
```bash
pip install textual>=0.48.0
pip install langchain langchain-google-genai langchain-pinecone pinecone unstructured-client
```

### Variables de entorno críticas
Para habilitar las integraciones avanzadas (RAG, agente AI, embeddings y búsquedas), configure las siguientes variables de entorno en su entorno (p.ej. un `.env` local o variables del sistema):

- `GOOGLE_API_KEY` : clave para Google Generative AI / embeddings.
- `PINECONE_API_KEY` : clave para Pinecone (vector DB) si se usa RAG.
- `UNSTRUCTURED_API_KEY` : clave para el servicio Unstructured (procesamiento de documentos).
- `MOUSER_API_KEY` : clave de Mouser (si usa búsqueda en catálogo en producción).
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` : opcional, si usa cache Redis.
```

### Ejecución
**Opción 1: Script de entrada** (recomendado)
**Opción recomendada: Script de entrada**

```bash
# Ejecuta la interfaz web (Gradio) por defecto
python run.py

# Ejecuta la TUI (Textual) - modo legacy
python run.py --tui
```

El script `run.py` detecta `--tui` para lanzar la versión de terminal; si no se pasa, intenta crear y lanzar la app Gradio.

Si necesita establecer variables de entorno en la misma línea (ejemplo mínimo):

```bash
GOOGLE_API_KEY=... PINECONE_API_KEY=... UNSTRUCTURED_API_KEY=... python run.py
```

Alternativa (directa, útil para debugging):

```bash
# Inicia la TUI directamente (si prefieres no usar `run.py --tui`)
python -m tutor_virtual.presentation.app
# O ejecutar el archivo directamente (menos recomendado)
python tutor_virtual/presentation/app.py
```

## 🎮 Guía de Uso

1. **Iniciar la aplicación**
   ```bash
   conda activate tutor-virtual
   python run.py
   ```

2. **Seleccionar topología**
   - Use las flechas ↑/↓ para navegar
   - Presione Enter para seleccionar

3. **Ingresar especificaciones**
   - Complete los campos con valores numéricos
   - Las unidades se muestran entre paréntesis: `Vin (V)`, `Fsw (Hz)`, etc.
   - Use Tab para navegar entre campos

4. **Calcular prediseño**
   - Presione `Ctrl+S` o `F5`
   - Los resultados se mostrarán con unidades automáticas:
     - Capacitores en µF/nF
     - Inductores en mH/µH
     - Frecuencias en kHz/MHz

5. **Limpiar formulario**
   - Clic en "Limpiar" o presione el botón correspondiente

6. **Salir**
   - Presione `Escape` o `Q`

## 🛠️ Desarrollo

### Estructura del Código

- **Domain Layer**: Lógica pura sin dependencias externas
  - `converters/designers.py`: 945 líneas, 13 clases concretas
  - `validation/rulesets.py`: Reglas específicas por topología
  
- **Application Layer**: Orquestación de casos de uso
  - `design_workflow.py`: Servicio principal de prediseño

- **Presentation Layer**: Interfaz Textual
- **Presentation Layer**: Interfaz (Web + TUI)
   - `app.py`: TUI (Textual) — wizard interactivo para diseño
   - `gradio_app.py`: Entrada Gradio/servidor web (experimental)
   - `gradio_adapter.py`: Lógica de adaptación entre Gradio y servicios (chat, diseño, documentos, tablas de componentes)
   - `translations.py`: Traducciones y mapeo de idiomas (i18n)
   - `spec_schema.py`: Definición de formularios por topología (ahora i18n-ready)

### Herramientas de Desarrollo

Instalar herramientas de calidad de código:
```bash
conda activate tutor-virtual
pip install black ruff mypy
```

Formatear código:
```bash
black tutor_virtual/
```

Linting:
```bash
ruff check tutor_virtual/
```

Type checking:
```bash
mypy tutor_virtual/
```


## 📊 Estado del Proyecto

### Progreso General: ~55% Completado (actualizado)

| Módulo | Estado | Completado |
|--------|--------|-----------|
| Core Domain (Converters) | ✅ | 100% |
| Validation Engine | ✅ | 100% |
| Application Services | ✅ | 100% |
| Presentation (TUI) | 🚧 | 95% |
| Persistence Layer | 🚧 | 10% |
| Component Catalog | 🚧 | 95% |
| AI/Chat Integration | 🚧 | 90% |
| Documentation | 🚧 | 65% |

## 📝 Licencia

TODO

## 👥 Autores
- **Gabriel Eduardo Mejía Ruíz** - Propuesta de idea y exposición de oportunidad
- **Juan Pablo Mejía Gómez** - Diseño de solución de software - [@Juanpa0128j](https://github.com/Juanpa0128j)

## 🙏 Agradecimientos

- Textual framework por la excelente librería de TUI
- Comunidad de electrónica de potencia por las referencias técnicas
- IEEE/IEC por los estándares de diseño
 - Gradio por facilitar la creación rápida de interfaces web experimentales
 - Pinecone por la solución de vector store que potencia las búsquedas por similaridad
 - LangChain por la infraestructura de agentes y orquestación de herramientas de LLM
 - Unstructured por las utilidades de procesamiento de documentos y extracción de texto

---

**Última actualización**: Diciembre 05, 2025
**Versión**: 0.1.0-alpha
