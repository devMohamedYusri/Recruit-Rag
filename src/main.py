from fastapi import FastAPI
from routes import base_router,data_router
from pymongo import AsyncMongoClient
from utils import get_settings

app=FastAPI()

@app.on_event("startup")
async def startup_db_client():
    settings=get_settings()
    app.mongodb_conn=AsyncMongoClient(settings.MONGO_DB)
    app.db_client=app.mongodb_conn[settings.DB_NAME]

@app.on_event("shutdown")
async def shutdown_db_client():
    app.mongodb_conn.close()
app.include_router(base_router)
app.include_router(data_router)