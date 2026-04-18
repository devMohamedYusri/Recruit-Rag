from fastapi import APIRouter, Request, HTTPException, status
from models import UserModel
from pydantic import BaseModel
from typing import Literal

billing_router = APIRouter(
    prefix="/api/v1/billing",
    tags=["api_v1", "billing", "plans"]
)

class PlanUpgradeRequest(BaseModel):
    plan: Literal["free", "starter", "pro", "agency", "payg"]

class AdminManualUpgradeRequest(BaseModel):
    user_email: str
    plan: Literal["free", "starter", "pro", "agency", "payg"]
    subscription_status: Literal["active", "trialing", "past_due", "canceled"] = "active"

@billing_router.get("/plan")
async def get_current_plan(request: Request):
    """Get the current user's plan and subscription status."""
    user_id = str(request.state.user["sub"])
    try:
        user_model = request.app.state.user_model
        user = await user_model.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "plan": user.plan,
            "subscription_status": user.subscription_status,
            "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
            "monthly_screening_count": user.monthly_screening_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@billing_router.post("/upgrade")
async def upgrade_plan(request: Request, upgrade_req: PlanUpgradeRequest):
    """
    Placeholder for plan upgrade logic.
    In a real system, this would redirct to Stripe or handle a session.
    For now, it just updates the plan if not 'free'.
    """
    user_id = str(request.state.user["sub"])
    try:
        user_model = request.app.state.user_model
        # Update user plan
        await user_model.update_user(user_id, {
            "plan": upgrade_req.plan,
            "subscription_status": "active"
        })
        
        return {"message": f"Successfully upgraded to {upgrade_req.plan} plan"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Admin Only ───────────────────────────────────────────────────────────

@billing_router.post("/admin/manual-upgrade")
async def admin_manual_upgrade(request: Request, admin_req: AdminManualUpgradeRequest):
    """Admin-only endpoint to manually set a user's plan."""
    # Check if requester is admin
    if request.state.user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
        
    try:
        user_model = request.app.state.user_model
        user = await user_model.get_user_by_email(admin_req.user_email)
        if not user:
            raise HTTPException(status_code=404, detail=f"User {admin_req.user_email} not found")
            
        await user_model.update_user(user.id, {
            "plan": admin_req.plan,
            "subscription_status": admin_req.subscription_status
        })
        
        return {"message": f"Manually updated user {admin_req.user_email} to {admin_req.plan} ({admin_req.subscription_status})"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
