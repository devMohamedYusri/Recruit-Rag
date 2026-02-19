# Screening result templates

ERROR_RESULT_TEMPLATE = {
    "fit_score": 0,
    "fit_label": "Error",
    "key_match_analysis": {
        "strengths": [],
        "missing_critical_skills": [],
        "experience_analysis": {
            "total_relevant_experience_years": 0.0,
            "required_years": 0.0,
            "seniority_level": "Unknown",
            "seniority_alignment": "Unknown",
            "role_fit_justification": "Screening failed"
        }
    },
    "flags": {"red_flags": ["Screening error"], "yellow_flags": []},
    "interview_prep": {"suggested_questions": []}
}

LIGHT_RESULT_TEMPLATE = {
    "fit_score": 0,
    "fit_label": "Light Match",
    "executive_summary": "Candidate processed via Light Screen (Standard Tier).",
    "key_match_analysis": {
        "strengths": [],
        "missing_critical_skills": [],
        "experience_analysis": {
            "total_relevant_experience_years": 0.0,
            "required_years": 0.0,
            "seniority_level": "Unverified",
            "seniority_alignment": "Unverified",
            "role_fit_justification": "Light Screen: Detailed analysis skipped."
        }
    },
    "flags": {"red_flags": [], "yellow_flags": []},
    "interview_prep": {"suggested_questions": []}
}

# Resume validation keywords
SECTION_KEYWORDS = [
    "experience", "education", "skills", "summary",
    "objective", "work", "projects", "certifications",
    "qualifications", "employment", "profile", "contact"
]

# File extension → MIME type mapping
MIME_MAP = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain"
}

# Prompt injection detection patterns
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "system prompt",
    "you are now",
    "jailbreak"
]

# Allowed resume file extensions (inside zips & for validation)
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "epub", "mobi"}

# ZIP content types
ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed"}

# LLM generation configs
SCREENING_GENERATION_CONFIG = {
    "temperature": 0.1,
    "max_output_tokens": 4096,
    "response_mime_type": "application/json"
}

EXTRACTION_GENERATION_CONFIG = {
    "temperature": 0.0,
    "max_output_tokens": 4096,
    "response_mime_type": "application/json"
}

BATCH_STRUCTURING_GENERATION_CONFIG = {
    "temperature": 0.0,
    "max_output_tokens": 8192,
    "response_mime_type": "application/json"
}

JSON_GENERATION_CONFIG = {
    "response_mime_type": "application/json"
}
