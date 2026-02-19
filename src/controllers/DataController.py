import os
import uuid
import aiofiles
import zipfile
import io
import logging
from models import AssetModel, ProjectModel
from models.DB_schemas.asset import Asset
from utils.config import Settings
from .BaseController import BaseController
from fastapi import UploadFile, HTTPException, status
from .ProjectController import ProjectController

project_controller = ProjectController()
logger = logging.getLogger(__name__)

class DataController(BaseController):
    def __init__(self):
        super().__init__()

    def validate_file_type(self, file_type: str) -> bool:
        return file_type in self.app_settings.FILE_ALLOWED_TYPES

    def validate_file_size(self, file_size: int) -> bool:
        return file_size < self.app_settings.FILE_MAX_SIZE_MB * self.app_settings.FILE_BYTES_TO_MB

    async def handle_upload(self, project_id: str, files: list[UploadFile], db_client):
        MAX_FILES = 200
        MAX_TOTAL_SIZE_MB = 50
        MAX_TOTAL_SIZE_BYTES = MAX_TOTAL_SIZE_MB * 1024 * 1024

        project_model = await ProjectModel.create_instance(db_client)
        asset_model = await AssetModel.create_instance(db_client)
        await project_model.get_project_or_create_one(project_id)

        uploaded_assets = []
        total_size = 0
        final_file_list = []

        # 1. Pre-check loop for total size (before unzip for optimization)
        # Note: We can't easily check total file count inside zips without reading them, 
        # so we check input file count first.
        if len(files) > MAX_FILES:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Too many files! Max limit is {MAX_FILES}."
            )

        for file in files:
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(0)
            total_size += size
            
        if total_size > MAX_TOTAL_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total upload size {total_size / (1024*1024):.2f}MB exceeds the {MAX_TOTAL_SIZE_MB}MB limit."
            )

        # 2. Processing Loop (Handle ZIPs)
        for file in files:
            content_type = file.content_type
            filename = file.filename
            
            # Basic zip detection
            if content_type in ["application/zip", "application/x-zip-compressed"] or filename.endswith(".zip"):
                try:
                    content = await file.read()
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        # Security check for zip bomb / too many files in zip
                        if len(z.infolist()) > MAX_FILES:
                             raise HTTPException(status_code=400, detail=f"ZIP file contains too many files ({len(z.infolist())}). Max is {MAX_FILES}.")
                        
                        for zip_filename in z.namelist():
                            if zip_filename.endswith("/") or zip_filename.startswith("__MACOSX") or zip_filename.startswith("."):
                                continue
                            
                            ext = zip_filename.split(".")[-1].lower()
                            # Allowed extensions check inside zip
                            if ext not in ["pdf", "docx", "txt", "epub", "mobi"]:
                                continue
                                
                            file_data = z.read(zip_filename)
                            # Flatten path - take only filename
                            clean_filename = zip_filename.replace("\\", "/").split("/")[-1]
                            
                            final_file_list.append({
                                "filename": clean_filename,
                                "content": file_data,
                                "size": len(file_data)
                            })
                except zipfile.BadZipFile:
                    raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {filename}")
            else:
                # Normal file
                content = await file.read()
                final_file_list.append({
                    "filename": filename,
                    "content": content,
                    "size": len(content)
                })

        # Re-check count after zip expansion
        if len(final_file_list) > MAX_FILES:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total files (including ZIP contents) {len(final_file_list)} exceeds limit of {MAX_FILES}."
            )

        # 3. Save files
        for file_data in final_file_list:
            original_name = file_data["filename"]
            content = file_data["content"]
            size = file_data["size"]
            
            file_path, file_name = self.generate_unique_file_name(original_name, project_id)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            async with aiofiles.open(file_path, 'wb') as out_file:
                await out_file.write(content)

            asset_obj = Asset(
                project_id=project_id,
                name=file_name,
                type="application/octet-stream",
                size_in_bytes=size,
                url=file_path
            )
            
            await asset_model.create_asset(asset_obj)
            uploaded_assets.append(asset_obj)
            
        return uploaded_assets

    def generate_unique_file_name(self, original_file_name: str, project_id: str) -> tuple[str, str]:
        extension = original_file_name.split(".")[-1]
        unique_id = str(uuid.uuid4())
        new_file_name = f"{project_id}_{unique_id}.{extension}"
        project_path = project_controller.get_project_asset_path(project_id)
        file_path = os.path.join(project_path, new_file_name)
        return file_path, new_file_name
