from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional, Literal
from datetime import datetime, timezone
from .types import PyObjectId

class UserUsage(BaseModel):
    jobs_count: int = 0
    cvs_analyzed_count: int = 0
    monthly_screenings_used: int = 0
    monthly_uploads_used: int = 0

class UserSettings(BaseModel):
    weekly_digests: bool = False
    marketing_offers: bool = False
    security_alerts: bool = True

class UserLimits(BaseModel):
    active_jobs: int = 1
    cv_per_job: int = 25
    storage_cap_cvs: Optional[int] = 100
    monthly_screenings: int = 25
    force_smart_screen: bool = True
    smart_screen_ratio: dict = Field(default_factory=lambda: {"fixed": 0.20})
    vector_search: bool = True
    cross_project_search: bool = False
    export: bool = False
    custom_weights: bool = False
    priority_queue: bool = False
    can_delete: bool = True

class User(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    email: EmailStr = Field(..., unique=True, index=True)
    password_hash: str
    role: Literal["user", "admin"] = "user"
    plan: Literal["free", "starter", "pro", "agency", "payg"] = "free"
    subscription_status: Literal["active", "trialing", "expired"] = "trialing"
    trial_ends_at: Optional[datetime] = None
    current_period_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_period_end: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    monthly_screening_count: int = 0
    usage: Optional[UserUsage] = None
    limits: Optional[UserLimits] = None
    settings: Optional[UserSettings] = Field(default_factory=UserSettings)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
    )

    @classmethod
    def get_indexes(cls):
        return [
            {
                "name": "email_index",
                "fields": [("email", 1)],
                "unique": True
            }
        ]
