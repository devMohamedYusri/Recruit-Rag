from .BaseController import BaseController
from models import UsageLogModel
from models.DB_schemas.usage_log import UsageLog
import logging

logger = logging.getLogger(__name__)

class UsageController(BaseController):
    def __init__(self, usage_model: UsageLogModel):
        super().__init__()
        self.usage_model = usage_model

    async def log_usage(
        self,
        project_id: str,
        model_id: str,
        action_type: str,
        usage_metadata: dict,
        file_id: str = None,
        latency_ms: int = 0
    ):
        if not usage_metadata:
            return
            
        try:
            log = UsageLog(
                project_id=project_id,
                file_id=file_id,
                model_id=model_id,
                action_type=action_type,
                prompt_tokens=usage_metadata.get("prompt_tokens", 0),
                completion_tokens=usage_metadata.get("completion_tokens", 0),
                total_tokens=usage_metadata.get("total_tokens", 0),
                latency_ms=latency_ms
            )
            await self.usage_model.log_usage(log)
        except Exception as e:
            logger.error(f"Failed to log usage: {e}")

    async def get_project_summary(self, project_id: str):
        return await self.usage_model.get_project_summary(project_id)

    async def get_usage_by_file(self, project_id: str):
        return await self.usage_model.get_usage_by_file(project_id)

    async def get_usage_logs(self, project_id: str, page: int = 1, page_size: int = 50):
        return await self.usage_model.get_usage_logs(project_id, page, page_size)
