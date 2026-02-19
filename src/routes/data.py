from fastapi import APIRouter,UploadFile,HTTPException,status,Request
from fastapi.responses import JSONResponse
from controllers import DataController
from models import ProjectModel,AssetModel,ResumeModel
from pydantic import BaseModel

data_controller=DataController()

data_router=APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1","data"]
)

@data_router.post("/upload/{project_id}",status_code=status.HTTP_201_CREATED)
async def upload_data(
    request:Request,
    project_id:str,
    files: list[UploadFile],
):
    
    project_model=await ProjectModel.create_instance(db_client=request.app.state.db_client)
    asset_model=await AssetModel.create_instance(db_client=request.app.state.db_client)
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
    