from fastapi import APIRouter, status, Request, HTTPException
from fastapi.responses import JSONResponse
from controllers import LLMController, VectorController
from models import ProjectModel, ResumeModel, JobDescriptionModel, AssetModel, ChunkModel
from models.DB_schemas.job_description import JobDescription
from .schema import JobDescriptionRequest, ProcessResumesRequest, ScreenRequest
import logging

logger = logging.getLogger("uvicorn.error")

llm_controller = LLMController()

llm_router = APIRouter(
    prefix="/api/v1/llm",
    tags=["api_v1", "llm", "screening"],
)


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
        generation_client = request.app.state.generation_client
        project_model = await ProjectModel.create_instance(
            db_client=request.app.state.db_client
        )
        resume_model = await ResumeModel.create_instance(
            db_client=request.app.state.db_client
        )
        chunk_model = await ChunkModel.create_instance(
            db_client=request.app.state.db_client
        )
        asset_model = await AssetModel.create_instance(
            db_client=request.app.state.db_client
        )

        project = await project_model.get_project_or_create_one(project_id)

        vector_db = request.app.state.vector_db
        embedding_client = request.app.state.embedding_client
        vector_controller = VectorController(
            vector_client=vector_db,
            embedding_model=embedding_client,
        )

        file_ids = process_request.file_ids or []

        result = await llm_controller.process_and_store_resumes(
            generation_client=generation_client,
            project_id=project_id,
            file_ids=file_ids,
            resume_model=resume_model,
            chunk_model=chunk_model,
            asset_model=asset_model,
            vector_controller=vector_controller,
            project=project,
            do_reset=process_request.do_reset
        )

        return JSONResponse(
            content={
                "signal": "resumes_processed",
                "project_id": project_id,
                **result
            },
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
):
    """Screen all (or selected) CVs against the cached job description."""
    try:
        generation_client = request.app.state.generation_client
        resume_model = await ResumeModel.create_instance(
            db_client=request.app.state.db_client
        )
        jd_model = await JobDescriptionModel.create_instance(
            db_client=request.app.state.db_client
        )

        results = await llm_controller.screen_candidates(
            generation_client=generation_client,
            resume_model=resume_model,
            jd_model=jd_model,
            project_id=project_id,
            file_ids=screen_request.file_ids,
            anonymize=screen_request.anonymize
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Screening error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screening failed: {str(e)}"
        )
