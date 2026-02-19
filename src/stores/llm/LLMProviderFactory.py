from .providers.GeminiProvider import GeminiProvider
from .LLMConfig import LLMConfig


class LLMProviderFactory:
    def __init__(self, config):
        self.config = config

    def create(self, provider: str, model_id: str = None):
        provider_key = provider.strip().lower()

        if provider_key == LLMConfig.PROVIDER_GEMINI:
            return GeminiProvider(
                model_id=model_id or self.config.GENERATION_MODEL_ID,
                api_key=self.config.GEMINI_API_KEY,
                embedding_model_id=self.config.EMBEDDING_MODEL_ID,
                embedding_dimension=self.config.EMBEDDING_MODEL_SIZE,
            )
        elif provider_key == LLMConfig.PROVIDER_GROQ:
            raise NotImplementedError(f"Groq provider is not implemented yet")
        else:
            raise ValueError(f"Invalid LLM provider: '{provider}'")