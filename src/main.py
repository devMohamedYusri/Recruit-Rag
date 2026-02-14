from fastapi import FastAPI
from routes import base_router,data_router
from pymongo import AsyncMongoClient
from utils import get_settings
from stores import LLMProviderFactory
from contextlib import asynccontextmanager
from stores import VectorDBFactory
from routes import vector_router

@asynccontextmanager
async def lifespan(app:FastAPI):
    settings=get_settings()
    app.state.mongodb_conn=AsyncMongoClient(settings.MONGO_DB)
    app.state.db_client=app.state.mongodb_conn[settings.DB_NAME]

    app.state.llm_provider_factory=LLMProviderFactory(settings)
    app.state.generation_client=app.state.llm_provider_factory.create(settings.GENERATION_BACKEND)
    app.state.embedding_client=app.state.llm_provider_factory.create(settings.EMBEDDING_BACKEND)

    app.state.vector_db_factory=VectorDBFactory(settings)
    app.state.vector_db=app.state.vector_db_factory.create_vector_db()
    await app.state.vector_db.initialize()
    try:
        yield
    finally:
        await app.state.mongodb_conn.close()
        app.state.llm_provider_factory=None
        app.state.generation_client=None
        app.state.embedding_client=None
        app.state.vector_db_factory=None
        app.state.vector_db=None
app = FastAPI(lifespan=lifespan)

app.include_router(base_router)
app.include_router(data_router)
app.include_router(vector_router)