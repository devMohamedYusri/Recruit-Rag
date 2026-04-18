import os
from dotenv import load_dotenv
load_dotenv()

# Detect Render production environment (Render sets RENDER=true automatically)
IS_RENDER = os.getenv("RENDER", "").lower() == "true"

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware

from routes import (
    base_router, data_router, vector_router, llm_router, 
    analytics_router, auth_router, billing_router, export_router
)
from pymongo import AsyncMongoClient
from utils import get_settings
from utils.auth_utils import decode_access_token
from stores import LLMProviderFactory, VectorDBFactory
from contextlib import asynccontextmanager

# Paths that bypass authentication and rate limiting
PUBLIC_PATHS = frozenset([
    "/api/v1/health",
    "/api/v1",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/health",
    "",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
])


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    import certifi
    app.state.mongodb_conn = AsyncMongoClient(
        settings.MONGO_DB,
        tlsCAFile=certifi.where(),
        maxPoolSize=50,
        minPoolSize=5,
        maxIdleTimeMS=30000,
        waitQueueTimeoutMS=5000,
    )
    db = app.state.mongodb_conn[settings.DB_NAME]
    app.state.db_client = db

    # Pre-initialize all models once at startup to avoid repeated index creation per-request
    from models import (
        AssetModel, ProjectModel, ResumeModel,
        JobDescriptionModel, ChunkModel, UsageLogModel,
        ScreeningResultModel, UserModel
    )
    app.state.asset_model = await AssetModel.create_instance(db)
    app.state.project_model = await ProjectModel.create_instance(db)
    app.state.resume_model = await ResumeModel.create_instance(db)
    app.state.jd_model = await JobDescriptionModel.create_instance(db)
    app.state.chunk_model = await ChunkModel.create_instance(db)
    app.state.usage_model = await UsageLogModel.create_instance(db)
    app.state.screening_result_model = await ScreeningResultModel.create_instance(db)
    app.state.user_model = await UserModel.create_instance(db)

    app.state.llm_provider_factory = LLMProviderFactory(settings)
    app.state.generation_client = app.state.llm_provider_factory.create(settings.GENERATION_BACKEND)
    app.state.embedding_client = app.state.llm_provider_factory.create(settings.EMBEDDING_BACKEND)
    app.state.screening_client = app.state.llm_provider_factory.create(
        settings.GENERATION_BACKEND, model_id=settings.SCREENING_MODEL_ID
    )

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
        app.state.screening_client = None
        app.state.vector_db_factory = None
        app.state.vector_db = None

settings = get_settings()
app = FastAPI(
    lifespan=lifespan,
    docs_url=None if IS_RENDER else "/docs",
    redoc_url=None if IS_RENDER else "/redoc",
    openapi_url=None if IS_RENDER else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path.rstrip("/")
    method = request.method
    
    if method == "OPTIONS":
        return await call_next(request)
        
    is_public = (
        path in PUBLIC_PATHS
    )

    if is_public:
        return await call_next(request)
    
    # Extract token from Header or Query Param
    auth_header = request.headers.get("Authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif request.query_params.get("token"):
        token = request.query_params.get("token")
        
    # Get origin for CORS headers
    origin = request.headers.get("origin")
    cors_headers = {}
    if origin:
        cors_headers["Access-Control-Allow-Origin"] = origin
        cors_headers["Access-Control-Allow-Credentials"] = "true"

    if not token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid authentication token"},
            headers=cors_headers
        )
    
    payload = decode_access_token(token)
    if not payload:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or expired token"},
            headers=cors_headers
        )
    
    request.state.user = payload
    return await call_next(request)

# Rate Limiter State
rate_limit_store = {}  # user_id -> (timestamp, count)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
        
    path = request.url.path.rstrip("/")
    if path in PUBLIC_PATHS:
         return await call_next(request)
    
    if not hasattr(request.state, "user"):
        return await call_next(request)
        
    user_id = request.state.user.get("sub")
    now = datetime.now(timezone.utc)
    
    if user_id not in rate_limit_store:
        rate_limit_store[user_id] = (now, 1)
    else:
        last_time, count = rate_limit_store[user_id]
        if (now - last_time).total_seconds() < 60:
            if count >= settings.RATE_LIMIT_REQUESTS_PER_MINUTE:
                origin = request.headers.get("origin")
                cors_headers = {}
                if origin:
                    cors_headers["Access-Control-Allow-Origin"] = origin
                    cors_headers["Access-Control-Allow-Credentials"] = "true"
                    
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests. Please slow down."},
                    headers=cors_headers
                )
            rate_limit_store[user_id] = (last_time, count + 1)
        else:
            rate_limit_store[user_id] = (now, 1)
            
    return await call_next(request)


# Register routes
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(export_router)
app.include_router(base_router)

app.include_router(data_router)
app.include_router(vector_router)
app.include_router(llm_router)
app.include_router(analytics_router)