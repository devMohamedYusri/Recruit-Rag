from .providers.GeminiProvider import GeminiProvider
from .providers.GroqProvider import GroqProvider

class LLMProviderFactory:
    def __init__(self,config:dict):
        self.config=config
    def create(self,provider:str):
        if provider==self.config.GEMINI:
            return GeminiProvider(
                model_id=self.config.GEMINI_GENERATION_MODEL_ID,
                api_key=self.config.GEMINI_API_KEY,
                embedding_model_id=self.config.EMBEDDING_MODEL_ID,
                embedding_dimention=self.config.EMBEDDING_DIMENSION
            )
        elif provider==self.config.GROQ:
            return GroqProvider(
                model_id=self.config.GROQ_GENERATION_MODEL_ID,
                api_key=self.config.GROQ_API_KEY,
                embedding_model_id=self.config.EMBEDDING_MODEL_ID,
                embedding_dimention=self.config.EMBEDDING_DIMENSION
            )
        else:
            raise ValueError("Invalid LLM provider")