class LLMConfig:
    """Central registry of available LLM models and provider identifiers."""

    # ── Provider Identifiers ─────────────────────────────────────
    PROVIDER_GEMINI = "gemini"
    PROVIDER_GROQ = "groq"

    # ── Default Model Settings ───────────────────────────────────
    DEFAULT_GEMINI_MODEL: str = "gemini-2.5-flash"
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
        "gemini-2.5-pro":        "gemini-2.5-pro",          # Best reasoning, long context
        "gemini-2.5-flash":      "gemini-2.5-flash",        # Fast + cost-efficient
        "gemini-2.5-flash-lite": "gemini-2.5-flash-lite",   # Budget, high-throughput
        "gemini-2.0-flash":      "gemini-2.0-flash",        # Fast multimodal
        "gemini-1.5-flash":      "gemini-1.5-flash",        # Legacy, large context
        "gemini-1.5-pro":        "gemini-1.5-pro",          # Legacy, more capable
        "gemini-3-pro-preview":  "gemini-3-pro-preview",    # Latest preview
    }