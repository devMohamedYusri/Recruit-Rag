from .BaseController import BaseController
from models.UsageLogModel import UsageLogModel
from models.DB_schemas.usage_log import UsageLog
import logging

logger = logging.getLogger(__name__)

class UsageController(BaseController):
    def __init__(self, usage_model: UsageLogModel):
        super().__init__()
        self.usage_model = usage_model

    async def log_usage(self, project_id: str, model_id: str, action_type: str, usage_metadata: dict):
        if not usage_metadata:
            return
            
        try:
            log = UsageLog(
                project_id=project_id,
                model_id=model_id,
                action_type=action_type,
                prompt_tokens=usage_metadata.get("prompt_tokens", 0),
                completion_tokens=usage_metadata.get("completion_tokens", 0),
                total_tokens=usage_metadata.get("total_tokens", 0)
            )
            await self.usage_model.log_usage(log)
        except Exception as e:
            logger.error(f"Failed to log usage: {e}")

    async def get_project_stats(self, project_id: str):
        return await self.usage_model.get_total_tokens_by_project(project_id)
