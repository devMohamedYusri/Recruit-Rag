from fastapi import APIRouter,Depends,Request
from utils import get_settings,Settings
base_router=APIRouter(
    prefix="/api/v1",
    tags=["api_v1"]
)

@base_router.get("/")

def welcome(app_settings:Settings=Depends(get_settings)):
    app_name=app_settings.APP_NAME
    app_version=app_settings.APP_VERSION
    return {
        "message": "Hello, welcome home",
        "version": app_version,
        "name": app_name
    }

@base_router.get("/debug/assets/{project_id}")
async def debug_assets(project_id: str, request: Request):
    db = request.app.state.db_client
    assets = await db.assets.find({"project_id": project_id}).to_list(length=None)
    return {
        "count": len(assets),
        "assets": [
            {"name": a.get("name"), "_id": str(a.get("_id"))} for a in assets
        ]
    }
