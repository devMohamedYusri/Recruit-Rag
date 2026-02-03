from fastapi import APIRouter,Depends
from utils import get_settings,settings
base_router=APIRouter(
    prefix="/api/v1",
    tags=["api_v1"]
)

@base_router.get("/")

def welcome(app_settings:settings=Depends(get_settings)):
    app_name=app_settings.APP_NAME
    app_version=app_settings.APP_VERSION
    return {
        "message ":"Hello,wolcome home",
        "version ":app_version,
        "name ":app_name
    }
