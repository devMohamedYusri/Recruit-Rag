from fastapi import APIRouter, Request, HTTPException, status, Query
from models.UsageLogModel import UsageLogModel

analytics_router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["api_v1", "analytics", "metrics"]
)

@analytics_router.get("/summary/{project_id}")
async def get_project_summary(request: Request, project_id: str):
    """Full project usage summary with breakdown by action type and model."""
    try:
        usage_model = await UsageLogModel.create_instance(request.app.state.db_client)
        summary = await usage_model.get_project_summary(project_id)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@analytics_router.get("/files/{project_id}")
async def get_usage_by_file(request: Request, project_id: str):
    """Per-file usage breakdown: tokens, latency, models, actions for each file."""
    try:
        usage_model = await UsageLogModel.create_instance(request.app.state.db_client)
        files = await usage_model.get_usage_by_file(project_id)
        return {"project_id": project_id, "files": files}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@analytics_router.get("/logs/{project_id}")
async def get_usage_logs(
    request: Request,
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200)
):
    """Paginated raw usage log listing."""
    try:
        usage_model = await UsageLogModel.create_instance(request.app.state.db_client)
        result = await usage_model.get_usage_logs(project_id, page, page_size)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
