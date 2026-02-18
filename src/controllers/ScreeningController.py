import json
import asyncio
import logging
from typing import Optional
from .BaseController import BaseController
from models.DB_schemas.resume import Resume
from utils.prompts import SCREENING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

ERROR_RESULT_TEMPLATE = {
    "fit_score": 0,
    "fit_label": "Error",
    "key_match_analysis": {"strengths": [], "missing_critical_skills": [], "experience_relevance": ""},
    "flags": {"red_flags": ["Screening error"], "yellow_flags": []},
    "interview_prep": {"suggested_questions": []}
}


class ScreeningController(BaseController):
    def __init__(self):
        super().__init__()

    async def build_jd_context(self, jd_model, project_id: str) -> str:
        jd = await jd_model.get_by_project_id(project_id)
        if not jd:
            raise ValueError(f"No job description found for project {project_id}")

        jd_context = f"=== JOB DESCRIPTION ===\nTitle: {jd.title}\n\n{jd.description}"
        if jd.prompt:
            jd_context += f"\n\nADDITIONAL SCREENING INSTRUCTIONS:\n{jd.prompt}"
        jd_context += "\n=== END JOB DESCRIPTION ==="
        return jd_context

    async def screen_single_cv(
        self, generation_client, resume: Resume, jd_context: str
    ) -> dict:
        prompt = f"""{jd_context}

{SCREENING_SYSTEM_PROMPT}

Now analyze the following resume:

RESUME (file_id: {resume.file_id}):
{resume.full_content}

Return ONLY the JSON screening result."""

        try:
            response = await generation_client.generate(
                prompt=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 4096,
                    "response_mime_type": "application/json"
                }
            )
            result = json.loads(response)
            result["cv_id"] = str(resume.id)
            result["candidate_name"] = resume.candidate_name
            result["contact_info"] = resume.contact_info
            return result
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for CV {resume.id}: {e}")
            return {
                **ERROR_RESULT_TEMPLATE,
                "cv_id": str(resume.id),
                "candidate_name": resume.candidate_name,
                "contact_info": resume.contact_info,
                "executive_summary": "Failed to parse LLM response",
            }
        except Exception as e:
            logger.error(f"Screening error for CV {resume.id}: {e}")
            return {
                **ERROR_RESULT_TEMPLATE,
                "cv_id": str(resume.id),
                "candidate_name": resume.candidate_name,
                "contact_info": resume.contact_info,
                "executive_summary": f"Screening failed: {str(e)}",
            }

    async def screen_candidates(
        self,
        generation_client,
        resume_model,
        jd_model,
        project_id: str,
        file_ids: Optional[list[str]] = None,
        anonymize: bool = True
    ) -> list[dict]:
        jd_context = await self.build_jd_context(jd_model, project_id)

        if file_ids:
            resumes = await resume_model.get_resumes_by_file_ids(project_id, file_ids)
        else:
            resumes = await resume_model.get_resumes_by_project_id(project_id)

        if not resumes:
            return []

        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)

        async def safe_screen(cv):
            async with sem:
                return await self.screen_single_cv(generation_client, cv, jd_context)

        results = await asyncio.gather(*[safe_screen(cv) for cv in resumes])

        if anonymize:
            for result in results:
                result["candidate_name"] = "[REDACTED]"
                result["contact_info"] = {}

        return list(results)
