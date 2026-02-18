from fastapi import APIRouter, status, Request, HTTPException
from fastapi.responses import JSONResponse
from controllers import VectorController
from models import ProjectModel
from .schema import SearchVectorsRequest
import logging

logger = logging.getLogger("uvicorn.error")

vector_router = APIRouter(
    prefix="/api/v1/vectors/candidate",
    tags=["api_v1", "vectors", "candidate"],
)

@vector_router.get("/info/{project_id}")
async def info_vectors(
    request: Request,
    project_id: str,
):
    try:
        vector_db = request.app.state.vector_db
        embedding_client = request.app.state.embedding_client

        vector_controller = VectorController(
            vector_client=vector_db,
            embedding_model=embedding_client,
        )

        project_model = await ProjectModel.create_instance(
            db_client=request.app.state.db_client
        )
        project = await project_model.get_project_or_create_one(project_id=project_id)

        collection_info = await vector_controller.vector_info(
            project_id=project.project_id,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"collection_info": collection_info},
        )
    except Exception as e:
        logger.error(f"Error getting info for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collection info: {str(e)}"
        )

@vector_router.post("/search/{project_id}")
async def search_vectors(
    request: Request,
    project_id: str,
    search_request: SearchVectorsRequest,
):
    try:
        vector_db = request.app.state.vector_db
        embedding_client = request.app.state.embedding_client

        vector_controller = VectorController(
            vector_client=vector_db,
            embedding_model=embedding_client,
        )

        project_model = await ProjectModel.create_instance(
            db_client=request.app.state.db_client
        )
        project = await project_model.get_project_or_create_one(project_id=project_id)

        results = await vector_controller.search_vectors(
            project=project,
            query_text=search_request.query_text,
            k=search_request.k,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "results": [
                    result.model_dump() 
                    for result in results
                ],
            },
        )
    except Exception as e:
        logger.error(f"Error searching vectors for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search vectors: {str(e)}"
        )
