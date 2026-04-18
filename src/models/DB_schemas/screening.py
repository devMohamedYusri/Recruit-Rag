from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal

class InterviewPrep(BaseModel):
    interview_recommendation: Optional[str] = Field(default=None)
    suggested_questions: List[str] = Field(default_factory=list)

class ScoringBreakdown(BaseModel):
    base_score: float = Field(default=0.0)
    skill_overlap: float = Field(default=0.0)
    experience_ratio: float = Field(default=0.0)
    required_keywords_ratio: float = Field(default=0.0)
    education_match: float = Field(default=0.0)

class LLMScreeningResponse(BaseModel):
    adjustment: int = Field(default=0, ge=-10, le=10, description="Adjustment integer between -10 and +10")
    reason: str = Field(default="", description="Short sentence explaining exactly what drove the score adjustment")
    summary: str = Field(default="", description="Short summary (executive summary) of the candidate's alignment")
    strengths: List[str] = Field(default_factory=list, description="Top 3-4 strengths")
    gaps: List[str] = Field(default_factory=list, description="Top 3-4 missing gaps or concerns")
    red_flags: List[str] = Field(default_factory=list, description="Serious concerns or deal-breakers")
    yellow_flags: List[str] = Field(default_factory=list, description="Minor concerns")
    interview_prep: Optional[InterviewPrep] = Field(default_factory=lambda: InterviewPrep())

class ScreeningResult(BaseModel):
    fit_score: float = Field(default=0.0, ge=0, le=100, description="Final score from 0 to 100")
    fit_label: Literal["Low Match", "Medium Match", "High Match", "Excellent Match", "Unknown", "Light Match", "Error"] = Field(default="Unknown")
    
    # Phase 1: Deterministic Math
    scoring_breakdown: ScoringBreakdown = Field(default_factory=ScoringBreakdown)
    
    # Phase 2: LLM Bounds
    adjustment: int = Field(default=0)
    reason: str = Field(default="")
    executive_summary: str = Field(default="")
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    yellow_flags: List[str] = Field(default_factory=list)
    interview_prep: Optional[InterviewPrep] = Field(default_factory=lambda: InterviewPrep())
    
    # Post-processing metadata
    cv_id: Optional[str] = Field(default=None)
    candidate_name: Optional[str] = Field(default=None)
    contact_info: Optional[dict] = Field(default_factory=dict)
    meta: Optional[dict] = Field(default_factory=dict)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fit_score": 77.4,
                "fit_label": "High Match",
                "scoring_breakdown": {
                    "base_score": 72.4,
                    "skill_overlap": 0.8,
                    "experience_ratio": 1.0,
                    "required_keywords_ratio": 0.5,
                    "education_match": 1.0
                },
                "adjustment": 5,
                "reason": "Strong open-source contributions offset lack of degree.",
                "risk_flags": ["No prior enterprise-scale deployment experience"],
                "executive_summary": "Solid frontend developer with deep React knowledge."
            }
        }
    )

class ContactInfo(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    location: Optional[str] = None

class JobHistory(BaseModel):
    title: Optional[str] = "Unknown"
    company: Optional[str] = "Unknown"
    industry_domain: Optional[str] = "Unknown"
    dates: Optional[str] = None
    description: Optional[str] = ""

class Education(BaseModel):
    degree: Optional[str] = "Unknown"
    institution: Optional[str] = "Unknown"
    dates: Optional[str] = None

class Project(BaseModel):
    name: Optional[str] = "Unknown"
    description: Optional[str] = ""

class ParsedData(BaseModel):
    summary: str = ""
    work_history: List[JobHistory] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)

class ExtractedResume(BaseModel):
    candidate_name: Optional[str] = "Unknown"
    contact_info: ContactInfo = Field(default_factory=ContactInfo)
    parsed_data: ParsedData = Field(default_factory=ParsedData)
