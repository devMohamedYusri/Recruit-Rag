import os
import uuid
import aiofiles
import zipfile
import io
import logging
from models import AssetModel, ProjectModel
from models.DB_schemas.asset import Asset
from .BaseController import BaseController
from fastapi import UploadFile, HTTPException, status
from .ProjectController import ProjectController
from utils.constants import ALLOWED_EXTENSIONS, ZIP_CONTENT_TYPES

project_controller = ProjectController()
logger = logging.getLogger(__name__)


class DataController(BaseController):
    def __init__(self):
        super().__init__()

    def validate_file_type(self, file_type: str) -> bool:
        return file_type in self.app_settings.FILE_ALLOWED_TYPES

    def validate_file_size(self, file_size: int) -> bool:
        return file_size < self.app_settings.FILE_MAX_SIZE_MB * self.app_settings.FILE_BYTES_TO_MB

    # ── Upload Pipeline ──────────────────────────────────────────────────

    async def handle_upload(self, project_id: str, files: list[UploadFile], db_client):
        max_files = self.app_settings.UPLOAD_MAX_FILES
        max_total_bytes = self.app_settings.UPLOAD_MAX_TOTAL_SIZE_MB * 1024 * 1024

        project_model = await ProjectModel.create_instance(db_client)
        asset_model = await AssetModel.create_instance(db_client)
        await project_model.get_project_or_create_one(project_id)

        # 1. Validate input count
        if len(files) > max_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Too many files! Max limit is {max_files}."
            )

        # 2. Validate total size
        total_size = self._calculate_total_size(files)
        if total_size > max_total_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total upload size {total_size / (1024*1024):.2f}MB exceeds the {self.app_settings.UPLOAD_MAX_TOTAL_SIZE_MB}MB limit."
            )

        # 3. Expand files (handle ZIPs)
        final_file_list = await self._expand_files(files, max_files)

        # 4. Re-check count after zip expansion
        if len(final_file_list) > max_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total files (including ZIP contents) {len(final_file_list)} exceeds limit of {max_files}."
            )

        # 5. Save files & create assets
        return await self._save_files(final_file_list, project_id, asset_model)

    # ── Private Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _calculate_total_size(files: list[UploadFile]) -> int:
        """Calculate total byte size of uploaded files."""
        total = 0
        for file in files:
            file.file.seek(0, 2)
            total += file.file.tell()
            file.file.seek(0)
        return total

    async def _expand_files(self, files: list[UploadFile], max_files: int) -> list[dict]:
        """Expand uploaded files, extracting ZIP contents into flat file list."""
        final_list = []

        for file in files:
            if self._is_zip_file(file):
                final_list.extend(await self._extract_zip(file, max_files))
            else:
                content = await file.read()
                final_list.append({
                    "filename": file.filename,
                    "content": content,
                    "size": len(content)
                })

        return final_list

    @staticmethod
    def _is_zip_file(file: UploadFile) -> bool:
        """Check if an uploaded file is a ZIP archive."""
        return (
            file.content_type in ZIP_CONTENT_TYPES
            or (file.filename and file.filename.endswith(".zip"))
        )

    async def _extract_zip(self, file: UploadFile, max_files: int) -> list[dict]:
        """Extract valid resume files from a ZIP archive."""
        extracted = []
        try:
            content = await file.read()
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if len(z.infolist()) > max_files:
                    raise HTTPException(
                        status_code=400,
                        detail=f"ZIP file contains too many files ({len(z.infolist())}). Max is {max_files}."
                    )

                for zip_filename in z.namelist():
                    if self._should_skip_zip_entry(zip_filename):
                        continue

                    ext = zip_filename.rsplit(".", 1)[-1].lower()
                    if ext not in ALLOWED_EXTENSIONS:
                        continue

                    file_data = z.read(zip_filename)
                    clean_filename = zip_filename.replace("\\", "/").split("/")[-1]

                    extracted.append({
                        "filename": clean_filename,
                        "content": file_data,
                        "size": len(file_data)
                    })
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {file.filename}")

        return extracted

    @staticmethod
    def _should_skip_zip_entry(filename: str) -> bool:
        """Check if a ZIP entry should be skipped (directories, macOS artifacts, hidden files)."""
        return (
            filename.endswith("/")
            or filename.startswith("__MACOSX")
            or filename.startswith(".")
        )

    async def _save_files(self, file_list: list[dict], project_id: str, asset_model) -> list[Asset]:
        """Save files to disk and create asset records in the database."""
        uploaded_assets = []

        for file_data in file_list:
            file_path, file_name = self.generate_unique_file_name(file_data["filename"], project_id)

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            async with aiofiles.open(file_path, 'wb') as out_file:
                await out_file.write(file_data["content"])

            asset_obj = Asset(
                project_id=project_id,
                name=file_name,
                type="application/octet-stream",
                size_in_bytes=file_data["size"],
                url=file_path
            )

            await asset_model.create_asset(asset_obj)
            uploaded_assets.append(asset_obj)

        return uploaded_assets

    def generate_unique_file_name(self, original_file_name: str, project_id: str) -> tuple[str, str]:
        extension = original_file_name.rsplit(".", 1)[-1]
        unique_id = str(uuid.uuid4())
        new_file_name = f"{project_id}_{unique_id}.{extension}"
        project_path = project_controller.get_project_asset_path(project_id)
        file_path = os.path.join(project_path, new_file_name)
        return file_path, new_file_name

    async def delete_asset(self, asset_id: str, asset_model):
        """Delete an asset from disk and database."""
        asset = await asset_model.get_asset_by_id(asset_id)
        if not asset:
            return False, f"Asset '{asset_id}' not found"

        # 1. Delete from disk
        if asset.url and os.path.exists(asset.url):
            try:
                os.remove(asset.url)
            except Exception as e:
                logger.warning(f"Failed to delete file from disk: {e}")

        # 2. Delete from DB
        success = await asset_model.delete_asset_by_id(asset_id)
        if success:
            return True, f"Asset '{asset_id}' deleted successfully"
        return False, "Failed to delete asset from database"
