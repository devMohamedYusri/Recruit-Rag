from fastapi import APIRouter, HTTPException, Depends, status, Request
from pydantic import BaseModel, EmailStr
from models import UserModel, User
from models.DB_schemas.user import UserSettings, UserUsage, UserLimits
from utils.auth_utils import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

class AuthRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: Request, auth_req: AuthRequest):
    db_client = request.app.state.db_client
    user_model = request.app.state.user_model
    
    existing_user = await user_model.get_user_by_email(auth_req.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(
        email=auth_req.email,
        password_hash=hash_password(auth_req.password)
    )
    await user_model.create_user(new_user)
    return {"message": "User registered successfully"}

@router.post("/login")
async def login(request: Request, auth_req: AuthRequest):
    db_client = request.app.state.db_client
    user_model = request.app.state.user_model
    
    user = await user_model.get_user_by_email(auth_req.email)
    if not user or not verify_password(auth_req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"access_token": access_token, "token_type": "bearer", "user": user.model_dump(by_alias=True)}

@router.put("/settings")
async def update_settings(request: Request, settings_req: UserSettings):
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_client = request.app.state.db_client
    user_model = request.app.state.user_model
    
    user = await user_model.get_user_by_email(request.state.user["email"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    await user_model.collection.update_one(
        {"_id": user.id}, 
        {"$set": {"settings": settings_req.model_dump()}}
    )
    return {"message": "Settings updated successfully", "settings": settings_req.model_dump()}

@router.get("/me", response_model=User)
async def get_me(request: Request):
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db_client = request.app.state.db_client
    user_model = request.app.state.user_model
    
    user = await user_model.get_user_by_email(request.state.user["email"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate real usage
    from models import ProjectModel, ResumeModel, UsageLogModel
    from utils.plan_config import PLANS
    from datetime import datetime, timezone
    
    project_model = request.app.state.project_model
    resume_model = request.app.state.resume_model
    usage_log_model = request.app.state.usage_model
    
    jobs_count = await project_model.collection.count_documents({"user_id": user.id})
    cvs_count = await resume_model.collection.count_documents({"user_id": user.id})
    
    # Calculate screenings and uploads this calendar month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    monthly_screenings_used = await usage_log_model.collection.count_documents({
        "user_id": user.id,
        "action_type": "screening",
        "created_at": {"$gte": month_start}
    })

    monthly_uploads_used = await usage_log_model.collection.count_documents({
        "user_id": user.id,
        "action_type": "resume_upload",
        "created_at": {"$gte": month_start}
    })
    
    plan_limits = PLANS.get(user.plan.lower(), PLANS["free"])
    
    user.usage = UserUsage(
        jobs_count=jobs_count,
        cvs_analyzed_count=cvs_count,
        monthly_screenings_used=monthly_screenings_used,
        monthly_uploads_used=monthly_uploads_used
    )
    
    user.limits = UserLimits(**plan_limits)
    
    return user
