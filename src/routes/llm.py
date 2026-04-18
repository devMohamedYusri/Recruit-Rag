from fastapi import APIRouter, status, Request, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from controllers import LLMController, VectorController, UsageController, PlanGuardService, TokenGuardService
from models import ProjectModel, ResumeModel, JobDescriptionModel, AssetModel, ChunkModel, UsageLogModel, ScreeningResultModel

from models.DB_schemas.job_description import JobDescription
from .schema import JobDescriptionRequest, ProcessResumesRequest, ScreenRequest
from stores import LLMProviderFactory
from utils.config import get_settings
from bson import ObjectId
import asyncio
import json
import logging

logger = logging.getLogger("uvicorn.error")

llm_controller = LLMController()

llm_router = APIRouter(
    prefix="/api/v1/llm",
    tags=["api_v1", "llm", "screening"],
)


# ── Dependency Helpers ───────────────────────────────────────────────────

def _get_models(request: Request) -> dict:
    """Retrieve all common pre-initialized data models from app state."""
    return {
        "project_model": request.app.state.project_model,
        "resume_model": request.app.state.resume_model,
        "jd_model": request.app.state.jd_model,
        "chunk_model": request.app.state.chunk_model,
        "asset_model": request.app.state.asset_model,
        "usage_controller": UsageController(request.app.state.usage_model),
        "screening_result_model": request.app.state.screening_result_model,
    }


def _get_vector_controller(request: Request) -> VectorController:
    """Build a VectorController from app state."""
    return VectorController(
        vector_client=request.app.state.vector_db,
        embedding_model=request.app.state.embedding_client,
    )


# ── Routes ───────────────────────────────────────────────────────────────

@llm_router.post("/job-description/{project_id}", status_code=status.HTTP_201_CREATED)
async def create_job_description(
    request: Request,
    project_id: str,
    jd_request: JobDescriptionRequest,
):
    """Create or update a job description for a project."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        # Plan guard: Check custom weights
        plan_guard = PlanGuardService(db)
        if jd_request.weights:
             await plan_guard.check_feature_allowed(user_id, "custom_weights")

        jd_model = request.app.state.jd_model

        jd = JobDescription(
            project_id=project_id,
            user_id=user_id,
            title=jd_request.title,
            description=jd_request.description,
            prompt=jd_request.prompt,
            weights=jd_request.weights,
            custom_rubric=jd_request.custom_rubric,
        )
        result = await jd_model.create_or_update_job_description(jd, user_id)

        return JSONResponse(
            content={
                "signal": "job_description_saved",
                "project_id": project_id,
                "title": result.title,
            },
            status_code=status.HTTP_201_CREATED
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job description error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save job description: {str(e)}"
        )


@llm_router.get("/job-description/{project_id}")
async def get_job_description(request: Request, project_id: str):
    """Retrieve the current job description for a project."""
    user_id = str(request.state.user["sub"])
    try:
        jd_model = request.app.state.jd_model
        jd = await jd_model.get_by_project_id(project_id, user_id)
        if not jd:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No job description found for project '{project_id}'"
            )

        data = jd.model_dump(by_alias=True)
        data["_id"] = str(data["_id"])
        data["user_id"] = str(data["user_id"])
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get job description error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve job description: {str(e)}"
        )


@llm_router.post("/process-resumes/{project_id}")
async def process_resumes(
    request: Request,
    project_id: str,
    process_request: ProcessResumesRequest,
    stream: bool = Query(default=False),
):
    """Extract, structure, chunk, and vectorize resumes for a project."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        settings = get_settings()
        generation_client = request.app.state.generation_client

        # Token Guard
        token_guard = TokenGuardService(db, settings)
        await token_guard.enforce_token_limit(project_id, user_id)

        extraction_client = LLMProviderFactory(settings).create(
            provider=settings.GENERATION_BACKEND,
            model_id=settings.CV_EXTRACTION_MODEL_ID
        )

        # Get user plan limit for CVs
        plan_guard = PlanGuardService(db)
        _, limits = await plan_guard.get_user_plan_limits(user_id)
        process_limit = limits.get("cv_per_job", 25)

        deps = _get_models(request)
        vector_controller = _get_vector_controller(request)
        project = await deps["project_model"].get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        if not stream:
            result = await llm_controller.process_and_store(
                generation_client=generation_client,
                project_id=project_id,
                user_id=user_id,
                file_ids=process_request.file_ids or [],
                resume_model=deps["resume_model"],
                chunk_model=deps["chunk_model"],
                asset_model=deps["asset_model"],
                vector_controller=vector_controller,
                project=project,
                do_reset=process_request.do_reset,
                extraction_client=extraction_client,
                usage_controller=deps["usage_controller"],
                limit=process_limit
            )
            return JSONResponse(
                content={"signal": "resumes_processed", "project_id": project_id, **result},
                status_code=status.HTTP_200_OK
            )

        # Streaming mode: return NDJSON progress
        progress_queue = asyncio.Queue()

        async def progress_callback(data: dict):
            await progress_queue.put(data)

        async def run_pipeline():
            try:
                await llm_controller.process_and_store(
                    generation_client=generation_client,
                    project_id=project_id,
                    user_id=user_id,
                    file_ids=process_request.file_ids or [],
                    resume_model=deps["resume_model"],
                    chunk_model=deps["chunk_model"],
                    asset_model=deps["asset_model"],
                    vector_controller=vector_controller,
                    project=project,
                    do_reset=process_request.do_reset,
                    extraction_client=extraction_client,
                    usage_controller=deps["usage_controller"],
                    progress_callback=progress_callback,
                    limit=process_limit
                )
            except Exception as e:
                await progress_queue.put({"phase": "error", "error": str(e)})
            finally:
                await progress_queue.put(None)

        async def event_generator():
            task = asyncio.create_task(run_pipeline())
            try:
                while True:
                    data = await progress_queue.get()
                    if data is None:
                        break
                    yield json.dumps(data) + "\n"
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Process resumes error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process resumes: {str(e)}"
        )


@llm_router.post("/screen/{project_id}")
async def screen_candidates(
    request: Request,
    project_id: str,
    screen_request: ScreenRequest,
    smart_screen: bool = True,
    stream: bool = False,
):
    """Screen all (or selected) CVs against the project's job description."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        # Plan guard: Check monthly screening limit (hard stop)
        plan_guard = PlanGuardService(db)
        await plan_guard.check_screening_limit(user_id)

        # Plan guard: Force smart screening for restricted plans
        user, limits = await plan_guard.get_user_plan_limits(user_id)
        must_force_smart = limits.get("force_smart_screen", False)
        process_limit = limits.get("cv_per_job", 25)
        plan_name = user.plan
        
        logger.info(f"Screening request for user {user_id} (plan: {plan_name}). must_force_smart: {must_force_smart}")

        if must_force_smart and not smart_screen:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your plan requires Smart Screening. Full LLM screening is not available on the free plan."
            )
        if must_force_smart:
            smart_screen = True

        # Plan guard: Get smart screen ratio config for tiered split
        ratio_config = limits.get("smart_screen_ratio")
        logger.info(f"Using ratio_config: {ratio_config} for plan {plan_name}")

        # Token Guard
        settings = get_settings()
        token_guard = TokenGuardService(db, settings)
        await token_guard.enforce_token_limit(project_id, user_id)

        deps = _get_models(request)
        project = await deps["project_model"].get_project_by_id(project_id, user_id)
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found."
            )
            
        file_ids = screen_request.file_ids
        if not file_ids:
            resumes = await deps["resume_model"].get_resumes_by_project_id(project_id, user_id)
            file_ids = [r.file_id for r in resumes]
            
        if process_limit and len(file_ids) > process_limit:
            file_ids = file_ids[:process_limit]
            
        screen_request.file_ids = file_ids
        
        # Check if JD exists
        jd_model = deps["jd_model"]
        jd = await jd_model.get_by_project_id(project_id, user_id)
        if not jd:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No job description found for project '{project_id}'."
            )

        
        screening_client = request.app.state.screening_client
        vector_controller = _get_vector_controller(request)

        common_args = {
            "generation_client": screening_client,
            "resume_model": deps["resume_model"],
            "jd_model": deps["jd_model"],
            "project_id": project_id,
            "user_id": user_id,
            "file_ids": screen_request.file_ids,
            "anonymize": screen_request.anonymize,
            "usage_controller": deps["usage_controller"],
            "screening_result_model": deps["screening_result_model"],
        }

        smart_args = {
            **common_args,
            "vector_controller": vector_controller,
            "project_model": deps["project_model"],
            "ratio_config": ratio_config,
        }

        if stream:
            generator = (
                llm_controller.smart_screen_candidates_stream(**smart_args)
                if smart_screen
                else llm_controller.screen_candidates_stream(**common_args)
            )
            # Increment screening count AFTER success (streaming is tricky, but let's assume it increments per file or at start)
            # For simplicity, we increment when the endpoint is called and starts processing.
            return StreamingResponse(generator, media_type="application/x-ndjson")

        results = (
            await llm_controller.smart_screen_candidates(**smart_args)
            if smart_screen
            else await llm_controller.screen_candidates(**common_args)
        )

        return JSONResponse(
            content={
                "signal": "screening_complete",
                "project_id": project_id,
                "total_screened": len(results),
                "results": results
            },
            status_code=status.HTTP_200_OK
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Screening error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screening failed: {str(e)}"
        )


@llm_router.get("/screen/{project_id}/results")
async def get_screening_results(
    request: Request,
    project_id: str,
    all_history: bool = Query(default=False)
):
    """Retrieve saved screening results for a project."""
    user_id = str(request.state.user["sub"])
    try:
        deps = _get_models(request)
        
        if all_history:
            results = await deps["screening_result_model"].get_results_by_project(project_id, user_id)
        else:
            results = await deps["screening_result_model"].get_latest_results_by_project(project_id, user_id)
        
        flattened_results = []
        for r in results:
            row = {**r.get("result", {})}
            row["_id"] = str(r["_id"])
            row["project_id"] = r["project_id"]
            row["file_id"] = r["file_id"]
            if "timestamp" in r and r["timestamp"]:
                row["timestamp"] = r["timestamp"].isoformat()
            
            flattened_results.append(row)
        
        return JSONResponse(content={"project_id": project_id, "results": flattened_results})
    except Exception as e:
        logger.error(f"Error fetching screening results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@llm_router.get("/screen/{project_id}/results/{file_id}")
async def get_latest_screening_result(
    request: Request,
    project_id: str,
    file_id: str
):
    """Retrieve the latest saved screening result for a specific resume."""
    user_id = str(request.state.user["sub"])
    try:
        deps = _get_models(request)
        result = await deps["screening_result_model"].get_latest_result_for_resume(project_id, file_id, user_id)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"No results found for {file_id}")
            
        result["_id"] = str(result["_id"])
        if "timestamp" in result and result["timestamp"]:
            result["timestamp"] = result["timestamp"].isoformat()
            
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching latest result: {e}")
        raise HTTPException(status_code=500, detail=str(e))
