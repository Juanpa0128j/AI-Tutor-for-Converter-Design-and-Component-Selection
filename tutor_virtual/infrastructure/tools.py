from typing import Dict, Any, Optional
from langchain_core.tools import tool
from tutor_virtual.application.services.design_workflow import DesignWorkflowService
from tutor_virtual.domain.converters import ConverterFactory, register_default_designers
from tutor_virtual.domain.validation import ValidationEngine, register_default_rules
from tutor_virtual.shared.dto import DesignRequest, DesignContext, ConverterSpec
from tutor_virtual.infrastructure.catalogs.mouser import MouserAdapter
from tutor_virtual.domain.components import ComponentRequirements, ComponentType
import asyncio
import os
from langchain_google_genai import ChatGoogleGenerativeAI


class DesignTool:
    """
    Wraps the DesignWorkflowService to be used as a LangChain tool.
    """
    def __init__(self):
        # Initialize domain services
        self.factory = ConverterFactory()
        register_default_designers(self.factory)
        
        self.validation_engine = ValidationEngine()
        register_default_rules(self.validation_engine)
        
        self.workflow = DesignWorkflowService(
            factory=self.factory,
            validation_engine=self.validation_engine
        )

    @tool
    def calculate_design(self, topology_id: str, inputs: Dict[str, float]) -> str:
        """
        Calculates the design for a power converter given the topology ID and input parameters.
        
        Args:
            topology_id: The ID of the topology (e.g., 'dc_dc_buck', 'dc_dc_boost').
            inputs: A dictionary of operating conditions (e.g., {'vin': 12.0, 'vo_target': 5.0, 'io_max': 2.0, 'fsw': 100000.0}).
                    Common keys: 'vin', 'vo_target', 'io_max', 'fsw' (frequency), 'delta_il_pct' (ripple current %), 'delta_vo_pct' (ripple voltage %).
        
        Returns:
            A string summary of the design results, including component values and efficiency.
        """
        # We need to instantiate the tool class to access self.workflow
        # But @tool decorator makes this a static function effectively if not careful.
        # For simplicity in this agent setup, we'll use a singleton or global instance pattern 
        # if we were defining it outside a class, but here we will define it as a method 
        # and bind it properly in the agent.
        
        # However, LangChain @tool decorator is best used on standalone functions.
        # Let's define a standalone function that uses a global/singleton service for now
        # to avoid complex binding issues with the decorator.
        pass

# Singleton instance for the tool function to use
_design_tool_instance = DesignTool()

@tool
def design_converter_tool(topology_id: str, inputs: Dict[str, float]) -> str:
    """
    Calculates the design for a power converter given the topology ID and input parameters.
    
    Args:
        topology_id: The ID of the topology. Options:
                     - 'dc_dc_buck' (Step-down)
                     - 'dc_dc_boost' (Step-up)
                     - 'dc_dc_buck_boost' (Step-up/down, negative output)
                     - 'dc_dc_cuk' (Step-up/down, negative output, low ripple)
                     - 'dc_dc_flyback' (Isolated)
        inputs: A dictionary of operating conditions.
                REQUIRED for most DC-DC:
                - 'vin': Input voltage (V)
                - 'vo_target': Target output voltage (V)
                - 'io_max': Maximum output current (A)
                - 'fsw': Switching frequency (Hz)
                OPTIONAL (defaults exist):
                - 'delta_il_pct': Inductor ripple current percentage (e.g., 20.0 for 20%)
                - 'delta_vo_pct': Output voltage ripple percentage (e.g., 1.0 for 1%)
    
    Returns:
        A text summary of the design result.
    """
    try:
        # Default constraints if not provided
        if "delta_il_pct" not in inputs:
            inputs["delta_il_pct"] = 20.0
        if "delta_vo_pct" not in inputs:
            inputs["delta_vo_pct"] = 1.0
            
        spec = ConverterSpec(
            topology_id=topology_id,
            operating_conditions=inputs,
            constraints={}
        )
        
        context = DesignContext(user_id="ai_agent", project_id="chat_session")
        request = DesignRequest(context=context, spec=spec)
        
        result = _design_tool_instance.workflow.run_predesign(request)
        
        # Format output for the LLM
        summary = f"Design Result for {topology_id}:\n"
        summary += f"Summary: {result.recommendation.summary}\n"
        
        summary += "Primary Values:\n"
        for k, v in result.predesign.primary_values.items():
            summary += f"- {k}: {v:.4f}\n"
            
        if result.losses.totals:
            summary += f"Efficiency: {result.recommendation.metadata.get('efficiency', 'N/A')}\n"
            summary += "Losses:\n"
            for k, v in result.losses.totals.items():
                summary += f"- {k}: {v:.4f} W\n"
                
        return summary
        
    except Exception as e:
        return f"Error calculating design: {str(e)}"

@tool
def derive_formula_tool(topology_name: str, variable_to_solve: str = "D") -> str:
    """
    Derives the steady-state equation for a given topology using symbolic math.
    Useful for explaining "How did we get this formula?".
    
    Args:
        topology_name: Name of the converter (e.g., 'buck', 'boost', 'buck-boost').
        variable_to_solve: The variable to solve for (default 'D' for duty cycle).
                           Options: 'D' (Duty Cycle), 'Vo' (Output Voltage), 'Vin' (Input Voltage).
    
    Returns:
        A string containing the LaTeX derivation steps.
    """
    try:
        import sympy as sp
        
        # Define common symbols
        Vin, Vo, D, T, L, di = sp.symbols('V_{in} V_{out} D T L \\Delta{i_L}')
        Ton = D * T
        Toff = (1 - D) * T
        
        steps = []
        steps.append(f"**Derivation for {topology_name.title()} Converter ({variable_to_solve}):**\n")
        
        if topology_name.lower() == "buck":
            # Inductor Voltage Balance: <v_L> = 0
            # ON State: v_L = Vin - Vo
            # OFF State: v_L = -Vo
            
            vl_on = Vin - Vo
            vl_off = -Vo
            
            steps.append("1. **Apply Volt-Second Balance on Inductor:**")
            steps.append("   In steady state, the average voltage across the inductor over one period is zero.")
            steps.append("   $$ \\langle v_L \\rangle = \\frac{1}{T} \\int_0^T v_L(t) dt = 0 $$")
            
            steps.append("2. **Analyze Switching States:**")
            steps.append(f"   - **Switch ON** (time $0$ to $DT$): Inductor connects $V_{{in}}$ to $V_{{out}}$.")
            steps.append(f"     $$ v_{{L,on}} = {sp.latex(vl_on)} $$")
            steps.append(f"   - **Switch OFF** (time $DT$ to $T$): Inductor connects ground to $V_{{out}}$.")
            steps.append(f"     $$ v_{{L,off}} = {sp.latex(vl_off)} $$")
            
            # Volt-Sec Equation
            volt_sec_eq = sp.Eq(vl_on * D + vl_off * (1 - D), 0)
            steps.append("3. **Write Balance Equation:**")
            steps.append(f"     $$ {sp.latex(vl_on)} \\cdot D + ({sp.latex(vl_off)}) \\cdot (1-D) = 0 $$")
            
            # Solve
            steps.append("4. **Solve:**")
            if variable_to_solve == "Vo":
                sol = sp.solve(volt_sec_eq, Vo)[0]
                steps.append(f"     $$ V_{{out}} = {sp.latex(sol)} $$")
            elif variable_to_solve == "Vin":
                sol = sp.solve(volt_sec_eq, Vin)[0]
                steps.append(f"     $$ V_{{in}} = {sp.latex(sol)} $$")
            else: # Solve for D
                sol = sp.solve(volt_sec_eq, D)[0]
                steps.append(f"     $$ D = {sp.latex(sol)} $$")
                
        elif topology_name.lower() == "boost":
            # ON State: v_L = Vin
            # OFF State: v_L = Vin - Vo
            vl_on = Vin
            vl_off = Vin - Vo
            
            steps.append("1. **Apply Volt-Second Balance on Inductor:**")
            steps.append("   $$ \\langle v_L \\rangle = 0 $$")
            
            steps.append("2. **Analyze Switching States:**")
            steps.append(f"   - **Switch ON**: Inductor charges from $V_{{in}}$.")
            steps.append(f"     $$ v_{{L,on}} = {sp.latex(vl_on)} $$")
            steps.append(f"   - **Switch OFF**: Inductor discharges to $V_{{out}}$.")
            steps.append(f"     $$ v_{{L,off}} = {sp.latex(vl_off)} $$")
            
            volt_sec_eq = sp.Eq(vl_on * D + vl_off * (1 - D), 0)
            steps.append("3. **Write Balance Equation:**")
            steps.append(f"     $$ {sp.latex(vl_on)} \\cdot D + ({sp.latex(vl_off)}) \\cdot (1-D) = 0 $$")
            
            steps.append("4. **Solve:**")
            if variable_to_solve == "Vo":
                sol = sp.solve(volt_sec_eq, Vo)[0]
                steps.append(f"     $$ V_{{out}} = {sp.latex(sol)} $$")
            else:
                sol = sp.solve(volt_sec_eq, D)[0]
                steps.append(f"     $$ D = {sp.latex(sol)} $$")
                
        else:
            return f"Derivation for {topology_name} not yet implemented."
            
        return "\n".join(steps)
        
    except Exception as e:
        return f"Error deriving formula: {str(e)}"

@tool
async def search_component_tool(
    component_type: str,
    voltage: float = 0.0,
    current: float = 0.0,
    capacitance: float = 0.0,
    inductance: float = 0.0
) -> str:
    """
    Searches for real electronic components from the Mouser catalog.
    
    Args:
        component_type: Type of component. Options: 'mosfet', 'diode', 'capacitor', 'inductor'.
        voltage: Max voltage rating (V) (for MOSFET, Diode, Capacitor).
        current: Max current rating (A) (for MOSFET, Diode, Inductor).
        capacitance: Capacitance value (F) (for Capacitor).
        inductance: Inductance value (H) (for Inductor).
    
    Returns:
        A list of top found components with pricing and availability.
    """
    try:
        # Map string type to Enum
        type_map = {
            'mosfet': ComponentType.MOSFET,
            'diode': ComponentType.DIODE,
            'capacitor': ComponentType.CAPACITOR,
            'inductor': ComponentType.INDUCTOR
        }
        
        c_type = type_map.get(component_type.lower())
        if not c_type:
            return f"Invalid component type: {component_type}. Supported: mosfet, diode, capacitor, inductor."
            
        # Build requirements
        reqs = ComponentRequirements(
            component_type=c_type,
            voltage_max=voltage if voltage > 0 else None,
            current_max=current if current > 0 else None,
            capacitance_min=capacitance if capacitance > 0 else None,
            inductance_min=inductance if inductance > 0 else None
        )
        
        # Initialize adapter (it manages its own env vars)
        async with MouserAdapter() as mouser:
            components = await mouser.search_components(reqs, limit=5)
            
        if not components:
            return "No components found matching the criteria."
            
        # Format output
        summary = f"Found {len(components)} results for {component_type}:\n"
        for c in components:
            summary += f"- {c.manufacturer} {c.part_number}: {c.description}\n"
            summary += f"  Price: ${c.price_usd:.2f} | Stock: {c.availability}\n"
            if c.datasheet_url:
                summary += f"  Datasheet: {c.datasheet_url}\n"
            summary += "\n"
            
        return summary

    except Exception as e:
        return f"Error searching components: {str(e)}"


@tool
def thermal_analysis_tool(
    power_loss: float,
    r_th_jc: float,
    r_th_cs: float = 0.5,
    r_th_sa: float = 0.0,
    t_amb: float = 25.0,
    max_tj: float = 0.0
) -> str:
    """
    Calculates Junction Temperature (Tj) or required Heatsink Thermal Resistance.
    Formula: Tj = Tamb + Ploss * (Rth_jc + Rth_cs + Rth_sa)
    
    Args:
        power_loss: Power dissipated by the component (W).
        r_th_jc: Thermal resistance Junction-to-Case (°C/W). Found in datasheet.
        r_th_cs: Thermal resistance Case-to-Sink (°C/W). Typical: 0.5 for thermal paste, 0.2 for greased pad.
        r_th_sa: Thermal resistance Sink-to-Ambient (°C/W). Heatsink spec. 0 if calculating required.
        t_amb: Ambient temperature (°C). Default 25.
        max_tj: Maximum allowed Junction Temperature (°C). If provided, tool calculates required Rth_sa.
    
    Returns:
        Analysis string with Tj or required heatsink spec.
    """
    try:
        # Scenario 1: Calculate Required Heatsink (Design Mode)
        if max_tj > 0:
            # Tj = Ta + P * (Rjc + Rcs + Rsa)
            # Tj - Ta = P * (Rjc + Rcs + Rsa)
            # (Tj - Ta)/P = Rjc + Rcs + Rsa
            # Rsa = (Tj - Ta)/P - (Rjc + Rcs)
            
            delta_t = max_tj - t_amb
            total_r_req = delta_t / power_loss
            r_req_sa = total_r_req - (r_th_jc + r_th_cs)
            
            summary = f"**Thermal Design Analysis**\n"
            summary += f"- Goal: Keep Tj <= {max_tj}°C with Tamb = {t_amb}°C\n"
            summary += f"- Dissipated Power: {power_loss} W\n"
            summary += f"- Max Total Thermal Resistance: {total_r_req:.2f} °C/W\n"
            
            if r_req_sa <= 0:
                summary += f"- **Result:** No heatsink needed! (Natural convection or case is enough if R_ja < {total_r_req:.2f})\n"
                summary += f"  (Calculated Reg R_sa is negative: {r_req_sa:.2f} °C/W)\n"
            else:
                summary += f"- **Result:** Required Heatsink R_th,sa < **{r_req_sa:.2f} °C/W**\n"
                summary += "  Recommendation: Select a heatsink with lower thermal resistance than this value."
                
            return summary
            
        # Scenario 2: Calculate Junction Temperature (Verification Mode)
        else:
            total_r = r_th_jc + r_th_cs + r_th_sa
            delta_t = power_loss * total_r
            tj = t_amb + delta_t
            
            summary = f"**Junction Temperature Estimation**\n"
            summary += f"- Total Thermal Resistance: {total_r:.2f} °C/W\n"
            summary += f"- Temperature Rise: {delta_t:.2f} °C\n"
            summary += f"- **Estimated Tj:** {tj:.2f} °C\n"
            
            if tj > 125:
                summary += "⚠️ **Warning:** Tj exceeds typical silicon limit (125°C - 150°C)!\n"
            elif tj > 100:
                summary += "⚠️ **Caution:** Tj is high. Consider better cooling.\n"
            else:
                summary += "✅ Tj is within safe limits for most components.\n"
                
            return summary
            
    except Exception as e:
        return f"Error calculating thermal metrics: {str(e)}"

@tool
def simulate_converter_tool(
    topology: str,
    vin: float,
    v_out: float,
    l_henry: float,
    c_farad: float,
    r_load_ohm: float,
    fsw_hz: float = 100000.0
) -> str:
    """
    Simulates the transient response of a power converter using ODE solving.
    Returns a summary of the simulation (ripple, settling time) and JSON data points.
    
    Args:
        topology: 'buck' or 'boost'.
        vin: Input voltage (V).
        v_out: Target Output voltage (V) (used to set duty cycle).
        l_henry: Inductance (H).
        c_farad: Capacitance (F).
        r_load_ohm: Load resistance (Ohm).
        fsw_hz: Switching frequency (Hz). Default 100kHz.
        
    Returns:
        Summary of simulation and time/voltage data points.
    """
    try:
        from tutor_virtual.application.services.simulation_service import simulation_service
        
        topo = topology.lower().strip()
        
        if "buck" in topo:
            result = simulation_service.simulate_buck(vin, v_out, l_henry, c_farad, r_load_ohm, fsw_hz)
        elif "boost" in topo:
            result = simulation_service.simulate_boost(vin, v_out, l_henry, c_farad, r_load_ohm, fsw_hz)
        else:
            return f"Simulation for topology '{topology}' not supported yet. Try 'buck' or 'boost'."
            
        # Analysis
        v_out_trace = result.v_out
        time_trace = result.time
        
        # Calculate ripple (last 20% of data assumed steady state-ish)
        n_points = len(v_out_trace)
        last_indices = int(n_points * 0.2)
        steady_state_v = v_out_trace[-last_indices:]
        
        v_avg = sum(steady_state_v) / len(steady_state_v)
        v_min = min(steady_state_v)
        v_max = max(steady_state_v)
        ripple_pp = v_max - v_min
        ripple_pct = (ripple_pp / v_avg) * 100 if v_avg > 0 else 0
        
        summary = f"**Simulation Results for {topo.title()}**\n"
        summary += f"- **Avg Output Voltage:** {v_avg:.4f} V\n"
        summary += f"- **Ripple (P-P):** {ripple_pp*1000:.2f} mV ({ripple_pct:.3f}%)\n"
        summary += f"- **Peak Current:** {max(result.i_ind):.4f} A\n"
        
        # Add limited data points for plotting if the agent wants to plot
        # Downsample to ~20 points for text representation, or return full list?
        # Tool returns string, so full list might be too long.
        # Let's return a condensed list.
        
        # stride = max(1, n_points // 20)
        # points = []
        # for i in range(0, n_points, stride):
        #     points.append(f"({time_trace[i]*1000:.2f}ms, {v_out_trace[i]:.2f}V)")
            
        # summary += f"\nTrace (t, Vo): {', '.join(points)}..."
        
        return summary
        
    except Exception as e:
        return f"Error simulating converter: {str(e)}"

@tool
def generate_quiz_question_tool(topic: str, difficulty: str = "intermediate") -> str:
    """
    Generates a multiple-choice quiz question on a specific power electronics topic.
    Returns the question, options, correct answer, and explanation.
    
    Args:
        topic: The topic (e.g., 'Buck Converter', 'MOSFET Switching', 'Thermal Design').
        difficulty: 'beginner', 'intermediate', or 'advanced'.
    """
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return "Error: GOOGLE_API_KEY not found."
            
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key)
        
        prompt = f"""
        Generate a single multiple-choice question about Power Electronics.
        Topic: {topic}
        Difficulty: {difficulty}
        
        Return ONLY a JSON object with this format (no markdown):
        {{
            "question": "The question text",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "Option A",
            "explanation": "Why it is correct"
        }}
        """
        
        response = llm.invoke(prompt)
        
        # Clean response if it contains markdown code blocks
        content = response.content.replace("```json", "").replace("```", "").strip()
        
        # Return as raw text for the Agent to process/present
        return content
        
    except Exception as e:
        return f"Error generating quiz: {str(e)}"


@tool
def rag_retrieval_tool(query: str, num_results: int = 5) -> str:
    """
    Search through uploaded course documents for relevant information.
    Use this when the user asks about topics that might be covered in their uploaded materials,
    or when they explicitly reference their documents.
    
    Args:
        query: The search query to find relevant content.
        num_results: Number of document chunks to retrieve (default 5).
    
    Returns:
        Formatted context from the most relevant uploaded documents.
    """
    try:
        from tutor_virtual.infrastructure.rag import get_rag_service
        
        rag_service = get_rag_service()
        
        # Check if there are any indexed documents
        indexed_docs = rag_service.get_indexed_documents()
        if not indexed_docs:
            return "No documents have been uploaded yet. Ask the user to upload course materials first."
        
        # Retrieve relevant context
        context = rag_service.retrieve_context_formatted(query, k=num_results)
        return context
        
    except Exception as e:
        return f"Error retrieving documents: {str(e)}"
