from fastapi import APIRouter, Depends
from utils import get_settings, Settings

base_router = APIRouter(
    prefix="/api/v1",
    tags=["api_v1"]
)


@base_router.get("/")
def welcome(app_settings: Settings = Depends(get_settings)):
    return {
        "message": "Hello, welcome home",
        "version": app_settings.APP_VERSION,
        "name": app_settings.APP_NAME
    }


@base_router.get("/health")
def health_check(app_settings: Settings = Depends(get_settings)):
    """Health check endpoint for frontend polling."""
    return {
        "status": "healthy",
        "version": app_settings.APP_VERSION,
        "name": app_settings.APP_NAME
    }
