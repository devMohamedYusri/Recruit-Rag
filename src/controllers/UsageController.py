from .BaseController import BaseController
from models import UsageLogModel
from models.DB_schemas.usage_log import UsageLog
import logging
import asyncio

logger = logging.getLogger(__name__)

SYSTEM_ACTION_TYPES = frozenset([
    "text_extraction_cpu", "db_bulk_insert", "qdrant_upsert",
    "event_loop_wait", "phase_wait"
])

class UsageController(BaseController):
    _db_sem = None # Throttled via lazy init

    def __init__(self, usage_model: UsageLogModel):
        super().__init__()
        self.usage_model = usage_model

    async def log_usage(
        self,
        project_id: str,
        user_id: object,
        model_id: str,
        action_type: str,
        usage_metadata: dict,
        file_id: str = None,
        latency_ms: int = 0
    ):
        if not usage_metadata:
            if action_type not in SYSTEM_ACTION_TYPES:
                logger.warning(f"No usage metadata provided for {action_type} (model: {model_id}) for project {project_id}")
            usage_metadata = {}
            
        try:
            prompt_tokens = usage_metadata.get("prompt_tokens", 0)
            completion_tokens = usage_metadata.get("completion_tokens", 0)
            total_tokens = usage_metadata.get("total_tokens", 0)
            
            if total_tokens == 0 and action_type not in ["text_extraction_cpu", "db_bulk_insert", "qdrant_upsert"]:
                 logger.info(f"UsageLog recorded with 0 tokens for {action_type}")

            log = UsageLog(
                project_id=project_id,
                user_id=user_id,
                file_id=file_id,
                model_id=model_id,
                action_type=action_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms
            )
            if not UsageController._db_sem:
                UsageController._db_sem = asyncio.Semaphore(25)

            async with UsageController._db_sem:
                await self.usage_model.log_usage(log)
        except Exception as e:
            logger.error(f"Failed to log usage: {e}")

    async def get_project_summary(self, project_id: str, user_id: object):
        return await self.usage_model.get_project_summary(project_id, user_id)

    async def get_usage_logs(self, user_id: object, project_id: str = None, page: int = 1, page_size: int = 50):
        return await self.usage_model.get_usage_logs(user_id, project_id, page, page_size)
