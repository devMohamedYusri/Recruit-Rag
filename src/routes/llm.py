from fastapi import APIRouter, status, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from controllers import LLMController, VectorController, UsageController
from models import ProjectModel, ResumeModel, JobDescriptionModel, AssetModel, ChunkModel
from models.UsageLogModel import UsageLogModel
from models.DB_schemas.job_description import JobDescription
from .schema import JobDescriptionRequest, ProcessResumesRequest, ScreenRequest
from stores.llm.LLMProviderFactory import LLMProviderFactory
from utils.config import get_settings
import logging

logger = logging.getLogger("uvicorn.error")

llm_controller = LLMController()

llm_router = APIRouter(
    prefix="/api/v1/llm",
    tags=["api_v1", "llm", "screening"],
)


# ── Dependency Helpers ───────────────────────────────────────────────────

async def _get_models(db_client) -> dict:
    """Instantiate all common data models in one call."""
    return {
        "project_model": await ProjectModel.create_instance(db_client),
        "resume_model": await ResumeModel.create_instance(db_client),
        "jd_model": await JobDescriptionModel.create_instance(db_client),
        "chunk_model": await ChunkModel.create_instance(db_client),
        "asset_model": await AssetModel.create_instance(db_client),
        "usage_controller": UsageController(
            await UsageLogModel.create_instance(db_client)
        ),
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
    try:
        jd_model = await JobDescriptionModel.create_instance(
            db_client=request.app.state.db_client
        )

        jd = JobDescription(
            project_id=project_id,
            title=jd_request.title,
            description=jd_request.description,
            prompt=jd_request.prompt,
            weights=jd_request.weights,
            custom_rubric=jd_request.custom_rubric,
        )
        result = await jd_model.create_or_update_job_description(jd)

        return JSONResponse(
            content={
                "signal": "job_description_saved",
                "project_id": project_id,
                "title": result.title,
            },
            status_code=status.HTTP_201_CREATED
        )
    except Exception as e:
        logger.error(f"Job description error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save job description: {str(e)}"
        )


@llm_router.post("/process-resumes/{project_id}")
async def process_resumes(
    request: Request,
    project_id: str,
    process_request: ProcessResumesRequest,
):
    """Extract, structure, chunk, and vectorize resumes for a project."""
    try:
        settings = get_settings()
        generation_client = request.app.state.generation_client

        extraction_client = LLMProviderFactory(settings).create(
            provider=settings.GENERATION_BACKEND,
            model_id=settings.CV_EXTRACTION_MODEL_ID
        )

        deps = await _get_models(request.app.state.db_client)
        vector_controller = _get_vector_controller(request)
        project = await deps["project_model"].get_project_or_create_one(project_id)

        result = await llm_controller.process_and_store(
            generation_client=generation_client,
            project_id=project_id,
            file_ids=process_request.file_ids or [],
            resume_model=deps["resume_model"],
            chunk_model=deps["chunk_model"],
            asset_model=deps["asset_model"],
            vector_controller=vector_controller,
            project=project,
            do_reset=process_request.do_reset,
            extraction_client=extraction_client,
            usage_controller=deps["usage_controller"]
        )

        return JSONResponse(
            content={"signal": "resumes_processed", "project_id": project_id, **result},
            status_code=status.HTTP_200_OK
        )
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
    try:
        generation_client = request.app.state.generation_client
        deps = await _get_models(request.app.state.db_client)
        vector_controller = _get_vector_controller(request)

        common_args = {
            "generation_client": generation_client,
            "resume_model": deps["resume_model"],
            "jd_model": deps["jd_model"],
            "project_id": project_id,
            "file_ids": screen_request.file_ids,
            "anonymize": screen_request.anonymize,
            "usage_controller": deps["usage_controller"],
        }

        smart_args = {
            **common_args,
            "vector_controller": vector_controller,
            "project_model": deps["project_model"],
        }

        if stream:
            generator = (
                llm_controller.smart_screen_candidates_stream(**smart_args)
                if smart_screen
                else llm_controller.screen_candidates_stream(**common_args)
            )
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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Screening error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screening failed: {str(e)}"
        )
