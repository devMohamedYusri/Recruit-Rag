from fastapi import APIRouter, Request, HTTPException, status, Query
from models import UsageLogModel, ProjectModel, ResumeModel, ScreeningResultModel

analytics_router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["api_v1", "analytics", "metrics"]
)

@analytics_router.get("/summary/{project_id}")
async def get_project_summary(request: Request, project_id: str):
    """Full project usage summary with breakdown by action type and model."""
    user_id = str(request.state.user["sub"])
    try:
        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        usage_model = request.app.state.usage_model
        summary = await usage_model.get_project_summary(project_id, user_id)
        return summary
    except HTTPException:
        raise
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
    """Paginated raw usage log listing for a specific project."""
    user_id = str(request.state.user["sub"])
    try:
        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        usage_model = request.app.state.usage_model
        result = await usage_model.get_usage_logs(user_id=user_id, project_id=project_id, page=page, page_size=page_size)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@analytics_router.get("/logs")
async def get_all_usage_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200)
):
    """Paginated raw usage log listing for the current user."""
    user_id = str(request.state.user["sub"])
    try:
        usage_model = request.app.state.usage_model
        result = await usage_model.get_usage_logs(user_id=user_id, page=page, page_size=page_size)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@analytics_router.get("/files/{project_id}")
async def get_files_breakdown(request: Request, project_id: str):
    """Per-file token and request breakdown for a project."""
    user_id = str(request.state.user["sub"])
    try:
        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        usage_model = request.app.state.usage_model
        result = await usage_model.get_files_breakdown(project_id, user_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@analytics_router.get("/user/stats")
async def get_user_stats(request: Request):
    """Aggregate high-level user statistics: jobs, resumes, shortlists, and time saved."""
    user_id = str(request.state.user["sub"])
    try:
        # 1. Total Jobs
        project_model = request.app.state.project_model
        total_jobs = await project_model.collection.count_documents({"user_id": user_id})
        
        # 2. Total Resumes Processed (Persistent via logs)
        usage_model = request.app.state.usage_model
        total_resumes = await usage_model.collection.count_documents({
            "user_id": user_id, 
            "action_type": "resume_upload"
        })
        
        # 3. Total Shortlisted Candidates (Persistent via logs)
        total_screenings = await usage_model.collection.count_documents({
            "user_id": user_id, 
            "action_type": "screening"
        })
        
        # 4. Estimated Time Saved
        # Industry averages (Realistic):
        # - Manual resume screening: ~3 minutes per resume.
        # - LLM extraction/structuring: ~1.5 minute.
        # Savings: ~1.5 minutes (90 seconds) per resume processed.
        # - Deep candidate analysis/shortlist: ~10 minutes manually vs ~6 minutes LLM.
        # Savings: ~4.0 minutes (240 seconds) per screening.
        
        time_saved_resumes_mins = total_resumes * 1.5
        time_saved_screenings_mins = total_screenings * 4.0
        total_time_saved_hours = round((time_saved_resumes_mins + time_saved_screenings_mins) / 60, 1)

        return {
            "total_jobs": total_jobs,
            "total_resumes_analyzed": total_resumes,
            "total_shortlists": total_screenings,
            "estimated_time_saved_hours": total_time_saved_hours,
            "time_saved_breakdown": {
                "per_resume_mins": 1.5,
                "per_job_analysis_mins": 4.0,
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

        
        # 3. Total Shortlisted Candidates (Persistent via logs)
        total_screenings = await usage_model.collection.count_documents({
            "user_id": user_id, 
            "action_type": "screening"
        })
        
        # 4. Estimated Time Saved
        # Industry averages (Realistic):
        # - Manual resume screening: ~3 minutes per resume.
        # - LLM extraction/structuring: ~1.5 minute.
        # Savings: ~1.5 minutes (90 seconds) per resume processed.
        # - Deep candidate analysis/shortlist: ~10 minutes manually vs ~6 minutes LLM.
        # Savings: ~4.0 minutes (240 seconds) per screening.
        
        time_saved_resumes_mins = total_resumes * 1.5
        time_saved_screenings_mins = total_screenings * 4.0
        total_time_saved_hours = round((time_saved_resumes_mins + time_saved_screenings_mins) / 60, 1)

        return {
            "total_jobs": total_jobs,
            "total_resumes_analyzed": total_resumes,
            "total_shortlists": total_screenings,
            "estimated_time_saved_hours": total_time_saved_hours,
            "time_saved_breakdown": {
                "per_resume_mins": 1.5,
                "per_job_analysis_mins": 4.0,
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
