from fastapi import FastAPI,APIRouter
import os
base_router=APIRouter(
    prefix="/api/v1",
    tags=["api_v1"]
)

@base_router.get("/")

def welcome():
    app_name=os.getenv("APP_NAME")
    app_version=os.getenv("APP_VERSION")
    return {
        "message":"Hello ,wolcome home",
        " version: ":app_version,
        "name ":app_name
    }
