from fastapi import APIRouter, status, Request, HTTPException
from fastapi.responses import JSONResponse
from controllers import VectorController, PlanGuardService
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
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        vector_db = request.app.state.vector_db
        embedding_client = request.app.state.embedding_client

        vector_controller = VectorController(
            vector_client=vector_db,
            embedding_model=embedding_client,
        )

        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id=project_id, user_id=user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        collection_info = await vector_controller.vector_info(
            project_id=project.project_id,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"collection_info": collection_info},
        )
    except HTTPException:
        raise
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
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        vector_db = request.app.state.vector_db
        embedding_client = request.app.state.embedding_client

        vector_controller = VectorController(
            vector_client=vector_db,
            embedding_model=embedding_client,
        )

        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id=project_id, user_id=user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching vectors for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search vectors: {str(e)}"
        )

@vector_router.post("/search")
async def search_vectors_body(
    request: Request,
    search_request: SearchVectorsRequest,
):
    # This might eventually support cross-project search (if plan allowed)
    project_id = search_request.project_id
    if not project_id:
        user_id = str(request.state.user["sub"])
        db = request.app.state.db_client
        # Plan guard: Check cross-project search
        plan_guard = PlanGuardService(db)
        await plan_guard.check_feature_allowed(user_id, "cross_project_search")
        
        # Implementation for cross-project search would go here
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cross-project search is not yet implemented"
        )
        
    return await search_vectors(request, project_id, search_request)
