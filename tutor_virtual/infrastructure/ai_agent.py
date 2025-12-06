"""
LangChain Agent for Power Electronics Tutoring.

Uses the new `create_agent` API from LangChain which handles:
- Tool execution loops automatically
- Memory persistence via checkpointer
- Clean message-based interface
"""
import os
from typing import Optional
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global checkpointer for session persistence
# In production, use a database-backed checkpointer like PostgresSaver
checkpointer = InMemorySaver()


class LangChainAgent:
    """
    Agent powered by Google's Gemini model via LangChain.
    Specialized in Power Electronics tutoring.
    
    Uses the new `create_agent` API which simplifies tool handling and memory.
    """
    
    SYSTEM_PROMPT = """
You are an expert AI Tutor in Power Electronics, designed to help students understand complex concepts, topologies, and component selection.

**Your Goal:**
Guide the student through their learning journey. Do not just give the answer; explain the "Why" and "How".

**Your Capabilities:**
- You can perform design calculations for power converters using the `design_converter_tool`.
- You can derive formulas step-by-step using the `derive_formula_tool`.
- You can search for real-world components using `search_component_tool`.
- You can perform thermal calculations using `thermal_analysis_tool`.
- You can simulate converters using `simulate_converter_tool`.
- You can generate quiz questions using `generate_quiz_question_tool`.
- You can search through uploaded course documents using `rag_retrieval_tool` to find relevant information.
- You can read datasheets from URLs using `read_datasheet_tool` to extract specific component data.

**Your Modes:**
1.  **Teacher Mode (Default):**
    -   Provide step-by-step explanations.
    -   Use the Socratic method: ask guiding questions if the student is stuck.
    -   When explaining values or design choices, always ask or explain "Why this value?".
    -   Use analogies where appropriate.

2.  **Comparison Mode:**
    -   When asked about differences (e.g., Buck vs. Boost), provide side-by-side comparisons.
    -   Highlight pros, cons, and typical use cases for each.

**Key Topics You Master:**
-   DC-DC Converters (Buck, Boost, Buck-Boost, Cuk, Flyback, etc.)
-   AC-DC Rectifiers
-   DC-AC Inverters
-   Component Selection (MOSFETs, Diodes, Inductors, Capacitors)
-   Thermal Management and Efficiency

**Tone:**
-   Encouraging, patient, and professional.
-   Technical but accessible.

**Format:**
-   Use Markdown for clarity (bolding, lists, code blocks).
-   Use LaTeX for formulas if needed (e.g., $V_{out} = D \\cdot V_{in}$).
-   **IMPORTANT:** If you use information retrieved from documents (via `rag_retrieval_tool`), you MUST explicitly cite the source and page number. Example: *(Source: "Chapter 1.pdf", Page 12)*.

If the user asks about something unrelated to Power Electronics or the course, politely steer them back to the topic.
"""
    
    def __init__(self, model_name: str = "gemini-2.5-flash", temperature: float = 0.7):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
            
        # Initialize tools
        from tutor_virtual.infrastructure.tools import (
            design_converter_tool, 
            derive_formula_tool, 
            search_component_tool, 
            thermal_analysis_tool, 
            simulate_converter_tool, 
            generate_quiz_question_tool,
            rag_retrieval_tool,
            read_datasheet_tool
        )
        tools = [
            design_converter_tool, 
            derive_formula_tool, 
            search_component_tool, 
            thermal_analysis_tool, 
            simulate_converter_tool, 
            generate_quiz_question_tool,
            rag_retrieval_tool,
            read_datasheet_tool
        ]
        
        # Initialize the LLM with API key
        model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=temperature,
        )
        
        # Create agent using the new API
        self.agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=self.SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )

    async def get_response(self, user_input: str, session_id: str = "default_session") -> str:
        """
        Generates a response to the user input, maintaining conversation history.
        
        Args:
            user_input: The user's message.
            session_id: Unique identifier for the conversation thread.
            
        Returns:
            The agent's response as a string.
        """
        config = {"configurable": {"thread_id": session_id}}
        
        try:
            # Invoke the agent with the user message
            result = await self.agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config
            )
            
            # Extract the last AI message content
            last_message = result["messages"][-1]
            content = last_message.content
            
            # Ensure content is a string (Gemini sometimes returns list of parts)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        parts.append(part["text"])
                    else:
                        parts.append(str(part))
                return " ".join(parts)
            return str(content)
            
        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def get_response_stream(self, user_input: str, session_id: str = "default_session"):
        """
        Streams tokens as they are generated by the LLM.
        
        Args:
            user_input: The user's message.
            session_id: Unique identifier for the conversation thread.
            
        Yields:
            str: Individual text tokens as they are generated.
        """
        config = {"configurable": {"thread_id": session_id}}
        
        try:
            async for token, metadata in self.agent.astream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="messages",
            ):
                # Only yield text content from the model node (not tool calls)
                if metadata.get('langgraph_node') == 'model':
                    content_blocks = getattr(token, 'content_blocks', None)
                    if content_blocks:
                        for block in content_blocks:
                            if isinstance(block, dict) and block.get('type') == 'text':
                                text = block.get('text', '')
                                if text:
                                    yield text
                    # Handle simple string content
                    elif hasattr(token, 'content') and isinstance(token.content, str):
                        if token.content:
                            yield token.content
        except Exception as e:
            yield f"Error generating response: {str(e)}"
