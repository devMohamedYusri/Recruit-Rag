from .providers.GeminiProvider import GeminiProvider
from .LLMConfig import LLMConfig


class LLMProviderFactory:
    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        provider_key = provider.strip().lower()

        if provider_key == LLMConfig.PROVIDER_GEMINI:
            return GeminiProvider(
                model_id=self.config.GENERATION_MODEL_ID,
                api_key=self.config.GEMINI_API_KEY,
                embedding_model_id=self.config.EMBEDDING_MODEL_ID,
                embedding_dimension=self.config.EMBEDDING_MODEL_SIZE,
            )
        elif provider_key == LLMConfig.PROVIDER_GROQ:
            raise NotImplementedError(f"Groq provider is not implemented yet")
            # return GroqProvider(
            #     model_id=self.config.GENERATION_MODEL_ID,
            #     api_key=self.config.GROQ_API_KEY,
            #     embedding_model_id=self.config.EMBEDDING_MODEL_ID,
            #     embedding_dimension=self.config.EMBEDDING_MODEL_SIZE,
            # )
        else:
            raise ValueError(f"Invalid LLM provider: '{provider}'")