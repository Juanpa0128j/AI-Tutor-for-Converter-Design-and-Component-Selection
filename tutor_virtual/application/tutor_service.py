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
