from fastapi import FastAPI
from routes import base_router,data_router
from pymongo import AsyncMongoClient
from utils import get_settings
from stores import LLMProviderFactory
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app:FastAPI):
    settings=get_settings()
    app.state.mongodb_conn=AsyncMongoClient(settings.MONGO_DB)
    app.state.db_client=app.state.mongodb_conn[settings.DB_NAME]

    app.state.llm_provider_factory=LLMProviderFactory(settings)
    app.state.generation_client=app.state.llm_provider_factory.create(settings.GENERATION_BACKEND)
    app.state.embedding_client=app.state.llm_provider_factory.create(settings.EMBEDDING_BACKEND)

    yield
    
    app.state.mongodb_conn.close()
    app.state.llm_provider_factory=None
    app.state.generation_client=None
    app.state.embedding_client=None
app = FastAPI(lifespan=lifespan)

app.include_router(base_router)
app.include_router(data_router)