class LLMConfig:
    groq = {
        "llama-3.1-8b":"llama-3.1-8b-instant",#Speed
        "llama-3.3-70b":"llama-3.3-70b-versatile",#balanced
        "gpt-oss-120B":"openai/gpt-oss-120b",#smartest
        "gpt-oss-20B":"openai/gpt-oss-20b",#faster than llama-3.1 8B and good with complex json
        "mixtral":"mixtral-8x7b-32768",#large context
    },
    gemini = {
        "gemini-1.5-pro":"gemini-1.5-pro",#more context
        "gemini-3-pro-preview":"Gemini-3-Pro-Preview"#reasoning and complex tasks
    }
    GEMINI_GENERATION_MODEL_ID: str = "gemini-2.0-flash",#gemini provider generation
    EMBEDDING_MODEL_ID: str = "gemini-embedding-001",#gemini provider generation embedding
    EMBEDDING_DIMENSION: int = 768
    GROQ_GENERATION_MODEL_ID: str = "llama-3.1-8b-instant"

    GEMINI="gemini"
    GROQ="groq"
