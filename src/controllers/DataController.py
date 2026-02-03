import os
import uuid
from .BaseController import BaseController
from fastapi import UploadFile
from .ProjectController import ProjectController
project_controller=ProjectController()
class DataController(BaseController):
    def __init__(self):
        super().__init__()
    def validate_file_type(self,file_type:str)->bool:
        return file_type in self.app_settings.FILE_ALLOWED_TYPES
    def validate_file_size(self,file_size:int)->bool:
        return file_size <self.app_settings.FILE_MAX_SIZE_MB *self.app_settings.FILE_BYTES_TO_MB
    
    async def validate_file(self,file:UploadFile)->dict:
            is_type_valid=self.validate_file_type(file.content_type)
            try:
                file.file.seek(0,2)
                file_size=file.file.tell()
                file.file.seek(0)
            except Exception:
                file_size=0
            is_size_valid=self.validate_file_size(file_size)
            return {
                "is_type_valid":is_type_valid,
                "is_size_valid":is_size_valid,
                "file_size":file_size,
                "is_valid":is_type_valid and is_size_valid
            }

    def generate_unique_file_name(self, original_file_name: str, project_id: str) -> str:
        extension = original_file_name.split(".")[-1]
        unique_id = str(uuid.uuid4())
        new_file_name = f"{project_id}_{unique_id}.{extension}"

        project_path=project_controller.get_project_asset_path(project_id)
        file_path = os.path.join(project_path, new_file_name)
        return file_path,new_file_name