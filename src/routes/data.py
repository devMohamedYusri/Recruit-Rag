from fastapi import APIRouter, UploadFile, HTTPException, status, Request, Query
from fastapi.responses import JSONResponse
from controllers import DataController, VectorController
from models import ProjectModel, AssetModel, ResumeModel, JobDescriptionModel, ChunkModel, UsageLogModel
from pydantic import BaseModel

data_controller = DataController()

data_router = APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1", "data"]
)


# ── Upload ───────────────────────────────────────────────────────────────

@data_router.post("/upload/{project_id}", status_code=status.HTTP_201_CREATED)
async def upload_data(
    request: Request,
    project_id: str,
    files: list[UploadFile],
):
    project_model = await ProjectModel.create_instance(db_client=request.app.state.db_client)
    await project_model.get_project_or_create_one(project_id=project_id)
    uploaded_assets = []

    try:
        raw_assets = await data_controller.handle_upload(project_id, files, request.app.state.db_client)
        uploaded_assets = [
            {
                "file_name": asset.name,
                "file_id": asset.name
            }
            for asset in raw_assets
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload files: {str(e)}")

    return JSONResponse(content={
        "message": f"Successfully uploaded {len(uploaded_assets)} files",
        "files": uploaded_assets,
        "status": "success"
    })


# ── Projects ─────────────────────────────────────────────────────────────

@data_router.post("/project", status_code=status.HTTP_201_CREATED)
async def create_project(request: Request, project_id: str):
    """Create a new project with the given ID."""
    try:
        project_model = await ProjectModel.create_instance(db_client=request.app.state.db_client)
        
        # Check if project already exists
        existing = await project_model.get_project_by_id(project_id)
        if existing:
            return {
                "project_id": project_id,
                "message": "Project already exists",
                "created": False
            }
        
        # Create new project
        from models.DB_schemas.project import Project
        new_project = Project(project_id=project_id)
        await project_model.create_project(new_project)
        
        return {
            "project_id": project_id,
            "message": "Project created successfully",
            "created": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_router.get("/projects")
async def list_projects(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    """List all projects with pagination."""
    try:
        project_model = await ProjectModel.create_instance(db_client=request.app.state.db_client)
        projects, total_pages = await project_model.get_all_projects(page=page, page_size=page_size)
        return {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "projects": [
                p.model_dump(by_alias=True, exclude_none=True)
                for p in projects
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_router.get("/project/{project_id}")
async def get_project_detail(request: Request, project_id: str):
    """Get project details with resume, asset, and JD counts."""
    try:
        db = request.app.state.db_client
        project_model = await ProjectModel.create_instance(db_client=db)
        project = await project_model.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        resume_model = await ResumeModel.create_instance(db_client=db)
        asset_model = await AssetModel.create_instance(db_client=db)
        jd_model = await JobDescriptionModel.create_instance(db_client=db)

        resumes = await resume_model.get_resumes_by_project_id(project_id)
        assets = await asset_model.get_assets_by_project_id(project_id)
        jd = await jd_model.get_by_project_id(project_id)

        return {
            "project_id": project.project_id,
            "resume_count": len(resumes),
            "asset_count": len(assets),
            "has_job_description": jd is not None,
            "job_description_title": jd.title if jd else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_router.delete("/project/{project_id}")
async def delete_project(request: Request, project_id: str):
    """Delete a project and ALL related data (assets, resumes, chunks, JD, vectors, usage logs)."""
    try:
        db = request.app.state.db_client
        project_model = await ProjectModel.create_instance(db_client=db)

        project = await project_model.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        resume_model = await ResumeModel.create_instance(db_client=db)
        asset_model = await AssetModel.create_instance(db_client=db)
        jd_model = await JobDescriptionModel.create_instance(db_client=db)
        chunk_model = await ChunkModel.create_instance(db_client=db)
        usage_model = await UsageLogModel.create_instance(db_client=db)

        deleted = {
            "resumes": await resume_model.delete_resumes_by_project_id(project_id),
            "assets": await asset_model.delete_assets_by_project_id(project_id),
            "chunks": await chunk_model.delete_chunks_by_project_id(project_id),
            "job_descriptions": await jd_model.delete_by_project_id(project_id),
            "usage_logs": await usage_model.delete_by_project_id(project_id),
        }

        # Delete vectors
        try:
            vector_db = request.app.state.vector_db
            embedding_client = request.app.state.embedding_client
            vector_controller = VectorController(
                vector_client=vector_db,
                embedding_model=embedding_client,
            )
            await vector_controller.delete_vectors(project_id)
            deleted["vectors"] = True
        except Exception:
            deleted["vectors"] = False

        await project_model.delete_project_by_id(project_id)
        deleted["project"] = True

        return {
            "message": f"Project '{project_id}' and all related data deleted",
            "deleted": deleted,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Resumes ──────────────────────────────────────────────────────────────

@data_router.get("/resumes/{project_id}")
async def list_resumes(request: Request, project_id: str):
    """List all resumes for a project (summary view without full_content)."""
    try:
        resume_model = await ResumeModel.create_instance(db_client=request.app.state.db_client)
        resumes = await resume_model.get_resumes_by_project_id(project_id)
        return {
            "project_id": project_id,
            "total": len(resumes),
            "resumes": [
                {
                    "_id": str(r.id),
                    "file_id": r.file_id,
                    "candidate_name": r.candidate_name,
                    "contact_info": r.contact_info,
                    "extraction_method": r.extraction_method,
                    "created_at": r.created_at,
                }
                for r in resumes
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_router.get("/resume/{cv_id}")
async def get_resume_by_id(request: Request, cv_id: str):
    """Retrieve full resume details (including candidate name and contact info) by cv_id."""
    try:
        resume_model = await ResumeModel.create_instance(db_client=request.app.state.db_client)
        resume = await resume_model.get_resume_by_id(cv_id)
        if not resume:
            raise HTTPException(status_code=404, detail=f"Resume with id '{cv_id}' not found")

        data = resume.model_dump(by_alias=True)
        data["_id"] = str(data["_id"])
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BatchResumeRequest(BaseModel):
    cv_ids: list[str]


@data_router.post("/resumes/batch")
async def get_resumes_batch(request: Request, batch_request: BatchResumeRequest):
    """Retrieve full resume details for multiple cv_ids at once."""
    try:
        resume_model = await ResumeModel.create_instance(db_client=request.app.state.db_client)
        resumes = await resume_model.get_resumes_by_ids(batch_request.cv_ids)

        results = []
        for resume in resumes:
            data = resume.model_dump(by_alias=True)
            data["_id"] = str(data["_id"])
            results.append(data)

        return {
            "total": len(results),
            "resumes": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Assets ───────────────────────────────────────────────────────────────

@data_router.get("/assets/{project_id}")
async def list_assets(request: Request, project_id: str):
    """List all uploaded file assets for a project."""
    try:
        asset_model = await AssetModel.create_instance(db_client=request.app.state.db_client)
        assets = await asset_model.get_assets_by_project_id(project_id)
        return {
            "project_id": project_id,
            "total": len(assets),
            "assets": [
                {
                    "_id": str(a.id),
                    "name": a.name,
                    "type": a.type,
                    "size_in_bytes": a.size_in_bytes,
                    "created_at": a.created_at,
                }
                for a in assets
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_router.delete("/asset/{asset_id}")
async def delete_asset(request: Request, asset_id: str):
    """Delete a single asset by its ID."""
    try:
        asset_model = await AssetModel.create_instance(db_client=request.app.state.db_client)
        success, message = await data_controller.delete_asset(asset_id, asset_model)
        
        if not success:
            status_code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(status_code=status_code, detail=message)
            
        return {"message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    