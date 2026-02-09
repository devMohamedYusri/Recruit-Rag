from fastapi import APIRouter,Depends,UploadFile,HTTPException,status,Request
from fastapi.responses import JSONResponse
from utils import get_settings,settings
from controllers import DataController,ProjectController,ProcessController
from .schema import processRequest
from models import ProjectModel,ChunkModel,AssetModel
data_controller=DataController()
project_controller=ProjectController()

data_router=APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1","data"]
)

@data_router.post("/upload/{project_id}",status_code=status.HTTP_201_CREATED)
async def upload_data(request:Request,project_id:str,files: list[UploadFile],
                app_settings:settings=Depends(get_settings)):
    
    project_model=await ProjectModel.create_instance(db_client=request.app.db_client)
    asset_model=await AssetModel.create_instance(db_client=request.app.db_client)
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
                "file_id": str(created_asset.id)
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {str(e)}")
        
    return JSONResponse(content={
        "message": f"Successfully uploaded {len(uploaded_assets)} files",
        "files": uploaded_assets,
        "status": "success"
    })



@data_router.post("/process/{project_id}",status_code=status.HTTP_200_OK)
async def process_data(requests:Request,project_id:str,request:processRequest):
    file_id=request.file_id

    chunk_model=await ChunkModel.create_instance(db_client=requests.app.db_client)
    project_model=await ProjectModel.create_instance(db_client=requests.app.db_client)

    project=await project_model.get_project_or_create_one(project_id=project_id)

    project_files_ids=[]
    if file_id is not None:
        project_files_ids.append(file_id)
    else:
        asset_model=await AssetModel.create_instance(db_client=requests.app.db_client)
        project_assets=await asset_model.get_assets_by_project_id(project_id=project.id)
        project_files_ids=[str(asset.name) for asset in project_assets]


    if not project_files_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail={
            "message":"No files found for processing.",
            "status":"error"
        })
    
    
    if request.do_reset:
        await chunk_model.delete_chunks_by_project_id(project_id=project.id)
    
    process_controller=ProcessController(project_id=project.id)
    results=[]
    for file_id in project_files_ids:
        count = await process_controller.process_one_file(
            chunk_model=chunk_model,
            file_id=file_id,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
        
        if count is None:
            raise HTTPException(status_code=500, detail="Processing failed for " + file_id)
        
        results.append({"file_id": file_id, "chunks_count": count})
    return JSONResponse(
        content={
            "file_count":len(results),
            "total_chunks_count":sum(r["chunks_count"] for r in results),
            "status":"success"
        }
    )