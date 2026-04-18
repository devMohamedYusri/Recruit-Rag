import logging
from datetime import datetime, timezone
from fastapi import HTTPException
from models import UsageLogModel

logger = logging.getLogger(__name__)

class TokenGuardService:
    def __init__(self, db_client: object, settings: object):
        self.db_client = db_client
        self.settings = settings

    async def check_token_limit(self, project_id: str, user_id: object) -> bool:
        """Check if the project has exceeded its monthly token limit."""
        usage_model = await UsageLogModel.create_instance(self.db_client)
        
        now = datetime.now(timezone.utc)
        summary = await usage_model.get_project_summary(project_id, user_id)
        total_tokens = summary.get("total_tokens", 0)
        
        if total_tokens >= self.settings.MAX_TOKENS_PER_PROJECT_PER_MONTH:
            logger.warning(f"Project {project_id} exceeded monthly token limit: {total_tokens}/{self.settings.MAX_TOKENS_PER_PROJECT_PER_MONTH}")
            return False
            
        return True

    async def enforce_token_limit(self, project_id: str, user_id: object):
        """Raises an exception if the token limit is exceeded."""
        if not await self.check_token_limit(project_id, user_id):
            raise HTTPException(
                status_code=429,
                detail=f"Monthly token limit for project exceeded ({self.settings.MAX_TOKENS_PER_PROJECT_PER_MONTH} tokens). Please contact support for an increase."
            )

