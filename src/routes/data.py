from fastapi import APIRouter,Depends,UploadFile,HTTPException,status,Request
from fastapi.responses import JSONResponse
from utils import get_settings,Settings
from controllers import DataController
from models import ProjectModel,AssetModel
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
    app_settings:Settings=Depends(get_settings)
):
    
    project_model=await ProjectModel.create_instance(db_client=request.app.state.db_client)
    asset_model=await AssetModel.create_instance(db_client=request.app.state.db_client)
    await project_model.get_project_or_create_one(project_id=project_id)
    uploaded_assets = []

    for file in files:
        valid_file = await data_controller.validate_file(file)
        if not valid_file.get("is_type_valid") or not valid_file.get("is_size_valid"):
            raise HTTPException(status_code=400, detail=f"Invalid file: {file.filename}")

        try:
            created_asset = await data_controller.save_and_record_asset(
                file, project_id, asset_model, app_settings
            )
            uploaded_assets.append({
                "file_name": created_asset.name,
                "file_id": created_asset.name
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {str(e)}")
        
    return JSONResponse(content={
        "message": f"Successfully uploaded {len(uploaded_assets)} files",
        "files": uploaded_assets,
        "status": "success"
    })
