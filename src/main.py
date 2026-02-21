from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import base_router, data_router, vector_router, llm_router, analytics_router
from pymongo import AsyncMongoClient
from utils import get_settings
from stores import LLMProviderFactory, VectorDBFactory
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app:FastAPI):
    settings = get_settings()
    app.state.mongodb_conn = AsyncMongoClient(settings.MONGO_DB)
    app.state.db_client = app.state.mongodb_conn[settings.DB_NAME]

    app.state.llm_provider_factory = LLMProviderFactory(settings)
    app.state.generation_client = app.state.llm_provider_factory.create(settings.GENERATION_BACKEND)
    app.state.embedding_client = app.state.llm_provider_factory.create(settings.EMBEDDING_BACKEND)

    app.state.vector_db_factory = VectorDBFactory(settings)
    app.state.vector_db = app.state.vector_db_factory.create_vector_db()
    await app.state.vector_db.initialize()
    try:
        yield
    finally:
        await app.state.mongodb_conn.close()
        app.state.llm_provider_factory = None
        app.state.generation_client = None
        app.state.embedding_client = None
        app.state.vector_db_factory = None
        app.state.vector_db = None

settings = get_settings()
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(base_router)
app.include_router(data_router)
app.include_router(vector_router)
app.include_router(llm_router)
app.include_router(analytics_router)