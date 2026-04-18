from fastapi import HTTPException, status
from models import UserModel, ProjectModel, ResumeModel
from utils.plan_config import PLANS
from datetime import datetime, timezone

class PlanGuardService:
    def __init__(self, db_client):
        self.db_client = db_client

    async def get_user_plan_limits(self, user_id):
        user_model = await UserModel.create_instance(self.db_client)
        user = await user_model.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        plan_name = user.plan.lower()
        return user, PLANS.get(plan_name, PLANS["free"])

    async def check_active_jobs_limit(self, user_id):
        user, limits = await self.get_user_plan_limits(user_id)
        project_model = await ProjectModel.create_instance(self.db_client)
        count = await project_model.count_documents({"user_id": user_id})
        
        if count >= limits["active_jobs"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Plan limit exceeded: Free plan allows {limits['active_jobs']} active job(s). Upgrade to create more."
            )

    async def check_cv_upload_limit(self, user_id, project_id, new_cv_count):
        user, limits = await self.get_user_plan_limits(user_id)
        
        from models import UsageLogModel
        usage_log_model = await UsageLogModel.create_instance(self.db_client)

        # Count uploads this calendar month (non-decreasing)
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        monthly_uploads = await usage_log_model.collection.count_documents({
            "user_id": user_id,
            "action_type": "resume_upload",
            "created_at": {"$gte": month_start}
        })

        # Check total storage/upload cap
        storage_cap = limits.get("storage_cap_cvs")
        if storage_cap is not None:
            if (monthly_uploads + new_cv_count) > storage_cap:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "limit_exceeded",
                        "type": "upload",
                        "message": f"Plan limit exceeded: Your plan allows {storage_cap} CV uploads per month. You have already used {monthly_uploads} uploads. Upgrade to continue."
                    }
                )

    async def check_screening_limit(self, user_id):
        """Enforce the monthly LLM screening limit. Raises 403 if exceeded."""
        user, limits = await self.get_user_plan_limits(user_id)
        monthly_limit = limits.get("monthly_screenings", 10)

        from models import UsageLogModel
        usage_log_model = await UsageLogModel.create_instance(self.db_client)

        # Count screenings this calendar month
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        monthly_count = await usage_log_model.collection.count_documents({
            "user_id": user_id,
            "action_type": "screening",
            "created_at": {"$gte": month_start}
        })


        if monthly_count >= monthly_limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "limit_exceeded",
                    "type": "screening",
                    "message": f"Plan limit exceeded: You have used {monthly_count}/{monthly_limit} screenings this month. Upgrade to continue."
                }
            )

    async def enforce_smart_screen(self, user_id) -> bool:
        """
        Returns True if smart_screen must be forced for this user's plan.
        """
        user, limits = await self.get_user_plan_limits(user_id)
        return limits.get("force_smart_screen", False)

    async def get_smart_screen_ratio(self, user_id) -> dict:
        """
        Returns the smar t_screen_ratio config for the user's plan.
        - {"fixed": 0.20} — fixed top-tier percentage
        - {"min": 0.10, "max": 0.40} — dynamic range
        """
        user, limits = await self.get_user_plan_limits(user_id)
        return limits.get("smart_screen_ratio", {"min": 0.10, "max": 0.40})

    async def check_feature_allowed(self, user_id, feature_name):
        user, limits = await self.get_user_plan_limits(user_id)
        if not limits.get(feature_name, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{feature_name}' is not available in your current plan. Upgrade to continue."
            )

    async def get_max_bulk_upload_limit(self, user_id) -> int:
        """Returns the maximum number of files allowed in a single upload for the user."""
        _, limits = await self.get_user_plan_limits(user_id)
        return limits.get("cv_per_job", 25)

