class LLMConfig:
    """Central registry of available LLM models and provider identifiers."""

    # ── Provider Identifiers ─────────────────────────────────────
    PROVIDER_GEMINI = "gemini"
    PROVIDER_GROQ = "groq"

    # ── Default Model Settings ───────────────────────────────────
    DEFAULT_GEMINI_MODEL: str = "gemini-2.0-flash"
    DEFAULT_GROQ_MODEL: str = "llama-3.1-8b-instant"
    DEFAULT_EMBEDDING_MODEL: str = "gemini-embedding-001"
    DEFAULT_EMBEDDING_DIMENSION: int = 768

    # ── Groq Model Catalog ───────────────────────────────────────
    GROQ_MODELS: dict[str, str] = {
        "llama-3.1-8b": "llama-3.1-8b-instant",         # Speed
        "llama-3.3-70b": "llama-3.3-70b-versatile",     # Balanced
        "gpt-oss-120B": "openai/gpt-oss-120b",          # Smartest
        "gpt-oss-20B": "openai/gpt-oss-20b",            # Fast + good JSON
        "mixtral": "mixtral-8x7b-32768",                 # Large context
    }

    # ── Gemini Model Catalog ─────────────────────────────────────
    GEMINI_MODELS: dict[str, str] = {
        "gemini-1.5-pro": "gemini-1.5-pro",              # More context
        "gemini-3-pro-preview": "Gemini-3-Pro-Preview",  # Reasoning
    }
