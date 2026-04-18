from fastapi import APIRouter, UploadFile, HTTPException, status, Request, Query
from fastapi.responses import JSONResponse
from controllers import DataController, VectorController, PlanGuardService
from models import ProjectModel, AssetModel, ResumeModel, JobDescriptionModel, ChunkModel, UsageLogModel, ScreeningResultModel
from models.DB_schemas.usage_log import UsageLog
from models.DB_schemas.project import Project
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel
from bson import ObjectId
import logging
import asyncio
logger = logging.getLogger(__name__)

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
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    
    # Use pre-initialized models from app.state
    project_model = request.app.state.project_model
    asset_model = request.app.state.asset_model
    usage_log_model = request.app.state.usage_model
    
    # Check if project exists and belongs to user
    project = await project_model.get_project_by_id(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # Plan guard: Check CV upload limit
    plan_guard = PlanGuardService(db)
    await plan_guard.check_cv_upload_limit(user_id, project_id, len(files))
    
    # Get plan-specific bulk upload limit (e.g., 300 for Pro, 1000 for Agency)
    max_bulk_limit = await plan_guard.get_max_bulk_upload_limit(user_id)

    uploaded_assets = []
    try:
        raw_assets = await data_controller.handle_upload(
            project_id=project_id, 
            files=files, 
            asset_model=asset_model, 
            user_id=user_id,
            max_files=max_bulk_limit
        )
        uploaded_assets = [
            {
                "file_name": asset.name,
                "file_id": asset.name
            }
            for asset in raw_assets
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed with unexpected error")
        raise HTTPException(status_code=500, detail=f"Failed to upload files: {str(e)}")

    # Log the uploads for non-decreasing limit tracking
    asyncio.create_task(_log_resume_uploads(usage_log_model, user_id, project_id, raw_assets))

    return JSONResponse(content={
        "message": f"Successfully uploaded {len(uploaded_assets)} files",
        "files": uploaded_assets,
        "status": "success"
    })

async def _log_resume_uploads(usage_log_model, user_id, project_id, files):
    """Log resume upload events for plan limit tracking (non-decreasing)."""
    try:
        for asset in files:
            log_entry = UsageLog(
                user_id=user_id,
                project_id=project_id,
                file_id=asset.name,
                action_type="resume_upload"
            )
            await usage_log_model.log_usage(log_entry)
    except Exception as e:
        logger.error(f"Failed to log resume uploads: {e}")


# ── Projects ─────────────────────────────────────────────────────────────

@data_router.get("/asset/{file_name}")
async def download_asset_file(request: Request, file_name: str):
    """Serve the physical uploaded file (e.g. PDF/DOCX) using FileResponse."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    
    asset_model = request.app.state.asset_model
    asset = await asset_model.collection.find_one({"name": file_name, "user_id": user_id})
    if not asset:
        raise HTTPException(status_code=404, detail="File asset metadata not found in database")
        
    project_id = asset["project_id"]
    from utils import get_settings
    import os
    from fastapi.responses import FileResponse
    
    settings = get_settings()
    file_path = os.path.join(settings.UPLOAD_DIRECTORY, project_id, file_name)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Physical file not found on disk")
        
    return FileResponse(file_path)


@data_router.post("/project", status_code=status.HTTP_201_CREATED)
async def create_project(request: Request, project_id: str):
    """Create a new project with the given ID."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    
    try:
        # Plan guard: Check active jobs limit
        plan_guard = PlanGuardService(db)
        await plan_guard.check_active_jobs_limit(user_id)

        project_model = request.app.state.project_model
        
        # Check if project already exists (any project with this ID)
        # Note: projectIDs should be unique globally if they are IDs, or scoped to user.
        # The current schema has project_id as unique.
        existing = await project_model.get_project_by_id(project_id, user_id)
        if existing:
            return {
                "project_id": project_id,
                "message": "Project already exists",
                "created": False
            }
        
        # Create new project
        try:
            new_project = Project(project_id=project_id, user_id=user_id)
            await project_model.create_project(new_project)
        except DuplicateKeyError:
             return {
                "project_id": project_id,
                "message": "Project already exists (duplicate key)",
                "created": False
            }
        
        return {
            "project_id": project_id,
            "message": "Project created successfully",
            "created": True
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project Creation Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")



@data_router.get("/projects")
async def list_projects(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    """List all projects for the current user with pagination, including counts and dates."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        project_model = request.app.state.project_model
        asset_model = request.app.state.asset_model
        
        projects, total_pages = await project_model.get_all_projects(user_id=user_id, page=page, page_size=page_size)
        
        # Enrich projects with candidate counts (using uploaded assets)
        enriched_projects = []
        for p in projects:
            assets = await asset_model.get_assets_by_project_id(p.project_id, user_id)
            data = p.model_dump(by_alias=True, exclude_none=True)
            data["resume_count"] = len(assets)
            data["created_at"] = p.created_at.isoformat() if hasattr(p, 'created_at') and p.created_at else None
            enriched_projects.append(data)

        return {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "projects": enriched_projects
        }
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@data_router.get("/resumes/all")
async def get_all_resumes(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
):
    """Retrieve all resumes for the current user across all projects with asset mapping."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        resume_model = request.app.state.resume_model
        asset_model = request.app.state.asset_model
        
        # We'll use the collection directly for a cross-project user query
        skip = (page - 1) * page_size
        cursor = resume_model.collection.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(page_size)
        records = await cursor.to_list(length=page_size)
        
        # Get all assets for this user to create a filename -> ID mapping
        assets = await asset_model.collection.find({"user_id": user_id}).to_list(length=None)
        asset_map = {a.get("name"): str(a.get("_id")) for a in assets}
        
        return {
            "total": len(records),
            "resumes": [
                {
                    "_id": str(r["_id"]),
                    "file_id": asset_map.get(r.get("file_id")), # Map internal name to secure hex ID
                    "candidate_name": r.get("candidate_name"),
                    "contact_info": r.get("contact_info"),
                    "project_id": r.get("project_id"),
                    "created_at": r.get("created_at").isoformat() if r.get("created_at") else None
                }
                for r in records if asset_map.get(r.get("file_id"))
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching all resumes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@data_router.get("/project/{project_id}")
async def get_project_detail(request: Request, project_id: str):
    """Get project details with resume, asset, and JD counts."""
    user_id = str(request.state.user["sub"])
    try:
        db = request.app.state.db_client
        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        resume_model = request.app.state.resume_model
        asset_model = request.app.state.asset_model
        jd_model = request.app.state.jd_model

        resumes = await resume_model.get_resumes_by_project_id(project_id, user_id)
        assets = await asset_model.get_assets_by_project_id(project_id, user_id)
        jd = await jd_model.get_by_project_id(project_id, user_id)

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
    """Delete a project and ALL related data (assets, resumes, chunks, JD, vectors, screening results, usage logs)."""
    user_id = str(request.state.user["sub"])
    try:
        db = request.app.state.db_client
        project_model = request.app.state.project_model
        resume_model = request.app.state.resume_model
        asset_model = request.app.state.asset_model
        jd_model = request.app.state.jd_model
        chunk_model = request.app.state.chunk_model
        usage_model = request.app.state.usage_model
        screening_result_model = request.app.state.screening_result_model

        # Check if project exists just for reporting purposes, don't block deletion of orphaned data
        project = await project_model.get_project_by_id(project_id, user_id)
        
        # Always run these deletes to sweep up any orphaned data for this user and project_id
        deleted = {
            "resumes": await resume_model.delete_resumes_by_project_id(project_id, user_id),
            "assets": await asset_model.delete_assets_by_project_id(project_id, user_id),
            "chunks": await chunk_model.delete_chunks_by_project_id(project_id, user_id),
            "job_descriptions": await jd_model.delete_by_project_id(project_id, user_id),
            "screening_results": 0, # Preserved for analytics/usage tracking
            "usage_logs": 0, # Preserved for non-decreasing limits
        }

        # Delete vectors
        try:
            vector_db = request.app.state.vector_db
            embedding_client = request.app.state.embedding_client
            vector_controller = VectorController(
                vector_client=vector_db,
                embedding_model=embedding_client,
            )
            # Only deletes the vector DB payload if there is one
            await vector_controller.delete_vectors(project_id)
            deleted["vectors"] = True
        except Exception as ve:
            logger.warning(f"Vector deletion error or doesn't exist for {project_id}: {ve}")
            deleted["vectors"] = False

        if project:
            await project_model.delete_project_by_id(project_id, user_id)
            deleted["project"] = 1
        else:
            deleted["project"] = 0

        # If absolutely nothing was found, and the project didn't exist, we can 404.
        # Otherwise, we successfully cleaned up SOME data.
        if not project and all(v == 0 or v is False for v in deleted.values()):
             raise HTTPException(status_code=404, detail=f"Project '{project_id}' and associated data not found")

        return {
            "message": f"Cleanup executed for project '{project_id}'",
            "deleted": deleted,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project Deletion Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Assets ───────────────────────────────────────────────────────────────

@data_router.get("/assets/{project_id}")
async def list_project_assets(project_id: str, request: Request):
    """List all assets for a specific project with obfuscated names and ID-based tracking."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        asset_model = request.app.state.asset_model
        project_model = request.app.state.project_model
        
        # Verify project exists and belongs to user
        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        assets = await asset_model.get_assets_by_project_id(project_id, user_id)
        
        # Obfuscate results for security
        return {
            "project_id": project_id,
            "total": len(assets),
            "assets": [
                {
                    "file_id": str(a.id), # Use MongoDB ID for frontend tracking
                    "file_name": "Resume.pdf", # Generic name for display
                    "status": "processed", # Simplify for UI
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "size_in_bytes": a.size_in_bytes,
                    "project_id": project_id
                }
                for a in assets
            ]
        }
    except Exception as e:
        logger.error(f"Error listing project assets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@data_router.get("/assets")
async def list_all_assets(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
):
    """List all assets for the current user with obfuscated names."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        asset_model = request.app.state.asset_model
        # Use collection directly for cross-project listing
        skip = (page - 1) * page_size
        cursor = asset_model.collection.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(page_size)
        asset_records = await cursor.to_list(length=page_size)
        
        # Calculate total pages (simplified)
        total_count = await asset_model.collection.count_documents({"user_id": user_id})
        total_pages = (total_count + page_size - 1) // page_size

        return {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total": total_count,
            "assets": [
                {
                    "file_id": str(asset["_id"]), # Use MongoDB ID
                    "file_name": "Resume.pdf", 
                    "status": "processed",
                    "created_at": asset.get("created_at").isoformat() if asset.get("created_at") else None,
                    "size_in_bytes": asset.get("size_in_bytes"),
                    "project_id": asset.get("project_id")
                }
                for asset in asset_records
            ]
        }
    except Exception as e:
        logger.error(f"Error listing all assets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@data_router.get("/asset/{asset_id}")
async def download_asset_by_id(request: Request, asset_id: str):
    """Securely serve asset file using its database identifier."""
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    try:
        from bson import ObjectId
        if not ObjectId.is_valid(asset_id):
            raise HTTPException(status_code=400, detail="Invalid asset ID format")
            
        asset_model = request.app.state.asset_model
        asset = await asset_model.collection.find_one({"_id": ObjectId(asset_id), "user_id": user_id})
        
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        file_path = asset.get("url")
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Physical file not found on server")
            
        return FileResponse(
            path=file_path,
            filename="Resume.pdf", # Generic filename for the download stream
            media_type="application/pdf"
        )
    except Exception as e:
        logger.error(f"Download failed for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@data_router.get("/resumes/{project_id}")
async def list_resumes(request: Request, project_id: str):
    """List all resumes for a project (summary view without full_content)."""
    user_id = str(request.state.user["sub"])
    try:
        resume_model = request.app.state.resume_model
        resumes = await resume_model.get_resumes_by_project_id(project_id, user_id)
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
    """Retrieve full resume details by cv_id."""
    user_id = str(request.state.user["sub"])
    try:
        resume_model = request.app.state.resume_model
        resume = await resume_model.get_resume_by_id(cv_id, user_id)
        if not resume:
            raise HTTPException(status_code=404, detail=f"Resume with id '{cv_id}' not found")

        data = resume.model_dump(by_alias=True)
        data["_id"] = str(data["_id"])
        data["user_id"] = str(data["user_id"])
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
    user_id = str(request.state.user["sub"])
    try:
        resume_model = request.app.state.resume_model
        resumes = await resume_model.get_resumes_by_ids(batch_request.cv_ids, user_id)

        results = []
        for resume in resumes:
            data = resume.model_dump(by_alias=True)
            data["_id"] = str(data["_id"])
            data["user_id"] = str(data["user_id"])
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
    user_id = str(request.state.user["sub"])
    try:
        asset_model = request.app.state.asset_model
        assets = await asset_model.get_assets_by_project_id(project_id, user_id)
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
    user_id = str(request.state.user["sub"])
    try:
        asset_model = request.app.state.asset_model
        success, message = await data_controller.delete_asset(asset_id, asset_model, user_id)
        
        if not success:
            status_code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(status_code=status_code, detail=message)
            
        return {"message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))