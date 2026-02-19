from fastapi import APIRouter, Request, HTTPException, status
from models.UsageLogModel import UsageLogModel

analytics_router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["api_v1", "analytics", "metrics"]
)

@analytics_router.get("/usage/{project_id}")
async def get_project_usage(request: Request, project_id: str):
    """Get aggregated usage stats for a project."""
    try:
        usage_model = await UsageLogModel.create_instance(request.app.state.db_client)
        stats = await usage_model.get_total_tokens_by_project(project_id)
        if stats:
            stats.pop("_id", None)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=str(e)
        )
