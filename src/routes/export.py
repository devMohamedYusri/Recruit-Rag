import csv
import io
import json
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import StreamingResponse
from models import ScreeningResultModel, ProjectModel
from controllers import PlanGuardService

export_router = APIRouter(
    prefix="/api/v1/export",
    tags=["api_v1", "export"]
)

@export_router.get("/project/{project_id}/csv")
async def export_project_csv(request: Request, project_id: str):
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    
    try:
        # Plan guard: Check if export is allowed
        plan_guard = PlanGuardService(db)
        await plan_guard.check_feature_allowed(user_id, "export")

        # Project ownership check
        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Fetch screening results
        screening_model = request.app.state.screening_result_model
        results = await screening_model.get_latest_results_by_project(project_id, user_id)
        
        if not results:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No screening results to export")

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers: Customize based on ScreeningResult schema
        writer.writerow(["Candidate Name", "Fit Score", "Executive Summary", "File ID", "Timestamp"])
        
        for r in results:
            res_data = r.get("result", {})
            writer.writerow([
                res_data.get("candidate_name", "Unknown"),
                res_data.get("fit_score", 0),
                res_data.get("executive_summary", ""),
                r.get("file_id", ""),
                r.get("timestamp", "").isoformat() if r.get("timestamp") else ""
            ])
            
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=project_{project_id}_export.csv"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@export_router.get("/project/{project_id}/json")
async def export_project_json(request: Request, project_id: str):
    user_id = str(request.state.user["sub"])
    db = request.app.state.db_client
    
    try:
        # Plan guard: Check if export is allowed
        plan_guard = PlanGuardService(db)
        await plan_guard.check_feature_allowed(user_id, "export")

        # Project ownership check
        project_model = request.app.state.project_model
        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Fetch screening results
        screening_model = request.app.state.screening_result_model
        results = await screening_model.get_latest_results_by_project(project_id, user_id)
        
        if not results:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No screening results to export")

        # Format results for export
        export_data = []
        for r in results:
            row = {**r}
            row["_id"] = str(row["_id"])
            row["user_id"] = str(row["user_id"])
            if "timestamp" in row:
                row["timestamp"] = row["timestamp"].isoformat()
            export_data.append(row)

        json_str = json.dumps(export_data, default=str)
        return StreamingResponse(
            io.BytesIO(json_str.encode()),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=project_{project_id}_export.json"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
