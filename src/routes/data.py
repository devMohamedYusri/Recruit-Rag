import os
from fastapi import APIRouter,Depends,UploadFile,HTTPException,status
from fastapi.responses import JSONResponse
from utils import get_settings,settings
from controllers import DataController
from controllers import ProjectController
import aiofiles
data_controller=DataController()
project_controller=ProjectController()

data_router=APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1","data"]
)

@data_router.post("/upload/{project_id}",status_code=status.HTTP_201_CREATED)
async def upload_data(project_id:str,file:UploadFile,
                app_settings:settings=Depends(get_settings)):
    valid_file= await data_controller.validate_file(file)

    if not valid_file.get("is_type_valid",False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail={
            "message":"Invalid file type uploaded.",
            "status":"error"
        })
    if not valid_file.get("is_size_valid",False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail={
            "message":"File size exceeds the maximum limit",
            "status":"error"
        })
    
    
    file_path,file_name=data_controller.generate_unique_file_name(file.filename,project_id)
    try:
         async with aiofiles.open(file_path,'wb') as out_file:
            while chunk:=await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                await out_file.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail={
            "message":"Failed to upload file.",
            "error":str(e),
            "status":"error"
        })
    return JSONResponse(
        content={
            "message":f"File uploaded successfully to project {project_id}",
            "file_name":file_name,
            "file_size":valid_file.get("file_size",0) / app_settings.FILE_BYTES_TO_MB,
            "status":"success"
        }
    )
