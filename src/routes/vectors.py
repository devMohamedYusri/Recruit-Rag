from fastapi import APIRouter, status, Request
from fastapi.responses import JSONResponse
from controllers import VectorController
from models import ProjectModel, ChunkModel
from .schema import UpsertVectorsRequest, SearchVectorsRequest
import logging

logger = logging.getLogger("uvicorn.error")

vector_router = APIRouter(
    prefix="/api/v1/vectors/candidate",
    tags=["api_v1", "vectors", "candidate"],
)


@vector_router.post("/upsert/{project_id}")
async def upsert_vectors(
    request: Request,
    project_id: str,
    vector_request: UpsertVectorsRequest,
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

        chunk_model = await ChunkModel.create_instance(
            db_client=request.app.state.db_client
        )
        project_chunks = await chunk_model.get_chunks_by_project_id(project_id=project_id, page=1, limit=0)

        if not project_chunks:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "No chunks found for this project. Process files first."},
            )

        await vector_controller.upsert_vectors(
            project=project,
            chunks=project_chunks,
            do_reset=vector_request.do_reset,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Vectors upserted successfully for project {project_id}",
                "chunks_count": len(project_chunks),
            },
        )
    except Exception as e:
        logger.error(f"Error upserting vectors for project {project_id}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": f"Failed to upsert vectors: {str(e)}"},
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
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": f"Failed to get collection info: {str(e)}"},
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
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": f"Failed to search vectors: {str(e)}"},
        )
