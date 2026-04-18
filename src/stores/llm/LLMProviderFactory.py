from .providers.GeminiProvider import GeminiProvider
from .providers.GroqProvider import GroqProvider
from .providers.FallbackProvider import FallbackProvider
from .LLMConfig import LLMConfig


from utils.config import Settings

class LLMProviderFactory:
    def __init__(self, config: Settings):
        self.config = config

    def create(self, provider: str, model_id: str = None):
        provider_key = provider.strip().lower()

        # 1. Instantiate Primary
        primary = None
        if provider_key == LLMConfig.PROVIDER_GEMINI:
            primary = GeminiProvider(
                model_id=model_id or self.config.GENERATION_MODEL_ID,
                api_key=self.config.GEMINI_API_KEY,
                embedding_model_id=self.config.EMBEDDING_MODEL_ID,
                embedding_dimension=self.config.EMBEDDING_MODEL_SIZE,
            )
        elif provider_key == LLMConfig.PROVIDER_GROQ:
            # Direct Groq usage
            return GroqProvider(
                 api_key=self.config.GROQ_API_KEY,
                 model_id=model_id or self.config.DEFAULT_GROQ_MODEL
            )
        else:
            raise ValueError(f"Invalid LLM provider: '{provider}'")

        # 2. Check Fallback (Only applies if Primary is Gemini for now)
        if self.config.ENABLE_LLM_FALLBACK and provider_key == LLMConfig.PROVIDER_GEMINI and self.config.GROQ_API_KEY:
            secondary = GroqProvider(
                api_key=self.config.GROQ_API_KEY,
                model_id=self.config.DEFAULT_GROQ_MODEL # Fallback model
            )
            return FallbackProvider(primary, secondary)
        
        return primary