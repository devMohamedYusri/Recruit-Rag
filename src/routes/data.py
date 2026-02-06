from fastapi import APIRouter,Depends,UploadFile,HTTPException,status,Request
from fastapi.responses import JSONResponse
from utils import get_settings,settings
from controllers import DataController,ProjectController,ProcessController
from .schema import processRequest
from models import ProjectModel,Chunk,ChunkModel,AssetModel,Asset
import aiofiles
import os

data_controller=DataController()
project_controller=ProjectController()

data_router=APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1","data"]
)

@data_router.post("/upload/{project_id}",status_code=status.HTTP_201_CREATED)
async def upload_data(request:Request,project_id:str,file:UploadFile,
                app_settings:settings=Depends(get_settings)):
    
    project_model=await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    await project_model.get_project_or_create_one(project_id=project_id)

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
    print(f"File saved at: {project_id}/{file_name}, full path: {file_path}, size: {os.path.getsize(file_path)} bytes, content type: {file.content_type}")
    asset_model=await AssetModel.create_instance(db_client=request.app.db_client)
    asset_record=Asset(
        project_id=project_id,
        name=file_name,
        type=file.content_type,
        size_in_bytes=os.path.getsize(file_path),
        url=file_path
    )
    created_asset=await asset_model.create_asset(asset_record)
    
    return JSONResponse(
        content={
            "message":f"File uploaded successfully",
            "file_name":file_name,
            "file_id":str(created_asset.id),
            "status":"success"
        }
    )




@data_router.post("/process/{project_id}",status_code=status.HTTP_200_OK)
async def process_data(requests:Request,project_id:str,request:processRequest):
    file_id=request.file_id
    chunk_size=request.chunk_size
    chunk_overlap=request.chunk_overlap
    do_reset=request.do_reset

    chunk_model=await ChunkModel.create_instance(
            db_client=requests.app.db_client
        )
    project_model=await ProjectModel.create_instance(
        db_client=requests.app.db_client
    )

    project=await project_model.get_project_or_create_one(project_id=project_id)
   
    process_controller=ProcessController(project_id=project_id)
    file_content=process_controller.load_document(file_id=file_id)
    chunks, file_texts, file_metadata=process_controller.process_document(
        file_content=file_content,
        file_id=file_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
        )
    if chunks is None or file_texts is None or file_metadata is None :
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail={
            "message":"Failed to process document.",
            "status":"error"
        })
    
    chunks_records=[Chunk(
        content=chunk.page_content,
        metadata=chunk.metadata,
        chunk_order=i+1,
        project_id=project.id
    ) for i, chunk in enumerate(chunks) ]
    if do_reset==True:
          _ =await chunk_model.delete_chunks_by_project_id(project_id=project.id)
    chunk_created=await chunk_model.create_chunks_bulk(chunks=chunks_records)

    return JSONResponse(
        content={
            "file_id":file_id,
            "chunks_count":chunk_created,
            "status":"success"
        }
    )