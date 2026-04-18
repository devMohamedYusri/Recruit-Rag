import os
import uuid
import aiofiles
import zipfile
import io
import logging
import asyncio
from models import AssetModel
from models.DB_schemas.asset import Asset
from .BaseController import BaseController
from fastapi import UploadFile, HTTPException, status
from .ProjectController import ProjectController
from utils.constants import ALLOWED_EXTENSIONS, ZIP_CONTENT_TYPES
import aioboto3

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

    async def handle_upload(self, project_id: str, files: list[UploadFile], asset_model, user_id: object, max_files: int = None):
        if max_files is None:
            max_files = self.app_settings.UPLOAD_MAX_FILES
        max_total_bytes = self.app_settings.UPLOAD_MAX_TOTAL_SIZE_MB * 1024 * 1024

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
        return await self._save_files(final_file_list, project_id, asset_model, user_id)

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

    @property
    def _s3_sem(self):
        if getattr(self, "__s3_sem", None) is None:
            import asyncio
            self.__s3_sem = asyncio.Semaphore(50)
        return self.__s3_sem

    @property
    def _db_sem(self):
        if getattr(self, "__db_sem", None) is None:
            import asyncio
            self.__db_sem = asyncio.Semaphore(10)
        return self.__db_sem

    async def _save_files(self, file_list: list[dict], project_id: str, asset_model, user_id: object) -> list[Asset]:
        """Save files to disk or S3/R2 and create asset records in parallel."""
        uploaded_assets = []
        is_cloud = bool(self.app_settings.S3_ENDPOINT_URL and self.app_settings.S3_BUCKET_NAME)

        async def upload_one(file_data, s3_client=None):
            file_path, file_name = self.generate_unique_file_name(file_data["filename"], project_id)
            final_url = ""

            # Phase 1: Network I/O (S3 or Disk) with high parallelism
            if is_cloud and s3_client:
                s3_key = f"projects/{project_id}/{file_name}"
                await s3_client.put_object(
                    Bucket=self.app_settings.S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=file_data["content"],
                    ContentType="application/octet-stream"
                )
                final_url = f"s3://{self.app_settings.S3_BUCKET_NAME}/{s3_key}"
            else:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                async with aiofiles.open(file_path, 'wb') as out_file:
                    await out_file.write(file_data["content"])
                final_url = file_path

            # Phase 2: Database Insert with throttled parallelism
            asset_obj = Asset(
                project_id=project_id,
                user_id=user_id,
                name=file_name,
                type="application/octet-stream",
                size_in_bytes=file_data["size"],
                url=final_url
            )

            async with self._db_sem:
                await asset_model.create_asset(asset_obj)
                
            return asset_obj

        if is_cloud:
            async with self._s3_sem:
                session = aioboto3.Session()
                async with session.client(
                    's3',
                    endpoint_url=self.app_settings.S3_ENDPOINT_URL,
                    aws_access_key_id=self.app_settings.S3_ACCESS_KEY_ID,
                    aws_secret_access_key=self.app_settings.S3_SECRET_ACCESS_KEY
                ) as s3_client:
                    # Launch all uploads concurrently
                    tasks = [upload_one(f, s3_client) for f in file_list]
                    uploaded_assets = await asyncio.gather(*tasks)
        else:
            async with self._s3_sem:
                # Parallel local disk writes
                tasks = [upload_one(f) for f in file_list]
                uploaded_assets = await asyncio.gather(*tasks)

        return list(uploaded_assets)

    def generate_unique_file_name(self, original_file_name: str, project_id: str) -> tuple[str, str]:
        extension = original_file_name.rsplit(".", 1)[-1]
        unique_id = str(uuid.uuid4())
        # We might want to include user_id in path for better isolation on disk too
        new_file_name = f"{project_id}_{unique_id}.{extension}"
        project_path = project_controller.get_project_asset_path(project_id)
        file_path = os.path.join(project_path, new_file_name)
        return file_path, new_file_name

    async def delete_asset(self, asset_id: str, asset_model, user_id: object):
        """Delete an asset from disk/S3 and database."""
        asset = await asset_model.get_asset_by_id(asset_id, user_id)
        if not asset:
            return False, f"Asset '{asset_id}' not found or access denied"

        # 1. Delete from storage (S3 or local disk)
        if asset.url:
            if asset.url.startswith("s3://"):
                try:
                    # s3://bucket-name/projects/proj-id/file.pdf -> key is projects/proj-id/file.pdf
                    bucket = self.app_settings.S3_BUCKET_NAME
                    s3_prefix = f"s3://{bucket}/"
                    if asset.url.startswith(s3_prefix):
                        s3_key = asset.url[len(s3_prefix):]
                        session = aioboto3.Session()
                        async with session.client(
                            's3',
                            endpoint_url=self.app_settings.S3_ENDPOINT_URL,
                            aws_access_key_id=self.app_settings.S3_ACCESS_KEY_ID,
                            aws_secret_access_key=self.app_settings.S3_SECRET_ACCESS_KEY
                        ) as s3_client:
                            await s3_client.delete_object(Bucket=bucket, Key=s3_key)
                except Exception as e:
                    logger.warning(f"Failed to delete file from S3: {e}")
            elif os.path.exists(asset.url):
                try:
                    os.remove(asset.url)
                except Exception as e:
                    logger.warning(f"Failed to delete file from disk: {e}")

        # 2. Delete from DB
        success = await asset_model.delete_asset_by_id(asset_id, user_id)
        if success:
            return True, f"Asset '{asset_id}' deleted successfully"
        return False, "Failed to delete asset from database"
