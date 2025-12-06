from tutor_virtual.infrastructure.ai_agent import LangChainAgent

class TutorService:
    """
    Service layer to manage the AI Tutor interactions.
    """
    
    def __init__(self):
        self.agent = LangChainAgent()
        
    async def ask_question(self, question: str, session_id: str = "default_user") -> str:
        """
        Process a user question through the AI Agent.
        """
        return await self.agent.get_response(question, session_id=session_id)
    
    async def ask_question_stream(self, question: str, session_id: str = "default_user"):
        """
        Stream tokens as the AI Agent generates a response.
        
        Yields:
            str: Individual text tokens as they are generated.
        """
        async for token in self.agent.get_response_stream(question, session_id=session_id):
            yield token

    async def update_context(self, session_id: str, design_data: dict):
        """
        Injects design context into the agent's conversation history.
        """
        try:
            topology = design_data.get('topology', 'Unknown')
            inputs = design_data.get('inputs', {})
            calculated = design_data.get('calculated_values', {})
            components = design_data.get('components', [])
            
            context_msg = (
                f"SYSTEM_UPDATE: The user has performed a design calculation.\n"
                f"Topology: {topology}\n"
                f"Inputs: {inputs}\n"
                f"Calculated Values: {calculated}\n"
            )
            
            if components:
                context_msg += "\nSelected Components:\n"
                for comp in components:
                    context_msg += f"- {comp.get('type')} ({comp.get('manufacturer')} {comp.get('part_number')}): {comp.get('description')}\n"
                    if comp.get('datasheet_url'):
                        context_msg += f"  Datasheet: {comp.get('datasheet_url')}\n"
                    if comp.get('attributes'):
                        context_msg += f"  Specs: {comp.get('attributes')}\n"
            else:
                context_msg += "\nNo specific components selected yet.\n"
                
            context_msg += "\nPlease use this context to answer subsequent questions about the design. If the user asks about implementation details, refer to the component datasheets using the read_datasheet_tool."
            
            # Send as a message to update history. 
            # We don't need the response.
            await self.agent.get_response(context_msg, session_id=session_id)
        except Exception as e:
            # Log error but don't crash
            print(f"Error updating context: {e}")
