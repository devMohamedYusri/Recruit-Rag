import json
import copy
import asyncio
import logging
from typing import Optional
from .BaseController import BaseController
from models.DB_schemas.resume import Resume
from utils.prompts import SCREENING_SYSTEM_PROMPT, JD_KEYWORD_EXTRACTION_PROMPT
from utils.constants import (
    ERROR_RESULT_TEMPLATE,
    LIGHT_RESULT_TEMPLATE,
    SCREENING_GENERATION_CONFIG,
    JSON_GENERATION_CONFIG,
    INJECTION_PATTERNS,
)
from utils.helpers import track_llm_call

logger = logging.getLogger(__name__)


class ScreeningController(BaseController):
    def __init__(self):
        super().__init__()

    # ── Private Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_error_result(resume: Resume, message: str) -> dict:
        """Build an error screening result for a resume."""
        return {
            **copy.deepcopy(ERROR_RESULT_TEMPLATE),
            "cv_id": str(resume.id),
            "candidate_name": resume.candidate_name,
            "contact_info": resume.contact_info,
            "executive_summary": message,
        }

    @staticmethod
    def _post_process_result(result: dict, resume: Resume, model_id: str, usage: dict) -> dict:
        """Calibrate scores, attach metadata, and inject candidate fields."""
        result["meta"] = {
            "method": "LLM Screen",
            "model": model_id,
            "usage": usage,
        }

        # Score Calibration: Avoid 0 for non-empty resumes
        if result.get("fit_score", 0) == 0 and len(resume.full_content.strip()) > 50:
            result["fit_score"] = 5

        # Suppress interview questions for very low matches
        if result.get("fit_score", 0) < 20:
            result["interview_prep"] = {
                "interview_recommendation": "Not recommended for interview based on current resume evidence.",
                "suggested_questions": []
            }

        result["cv_id"] = str(resume.id)
        result["candidate_name"] = resume.candidate_name
        result["contact_info"] = resume.contact_info
        return result

    @staticmethod
    def _anonymize_results(results) -> None:
        """Redact PII from a list of screening results (in-place)."""
        for result in results:
            result["candidate_name"] = "[REDACTED]"
            result["contact_info"] = {}

    async def _fetch_resumes(self, resume_model, project_id: str, file_ids: Optional[list[str]] = None) -> list:
        """Fetch resumes by project, optionally filtered by file_ids."""
        if file_ids:
            return await resume_model.get_resumes_by_file_ids(project_id, file_ids)
        return await resume_model.get_resumes_by_project_id(project_id)

    async def _run_concurrent(self, fn, items: list) -> list:
        """Run an async function over items with a concurrency semaphore."""
        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)

        async def limited(item):
            async with sem:
                return await fn(item)

        return list(await asyncio.gather(*[limited(item) for item in items]))

    # ── JD Context ───────────────────────────────────────────────────────

    async def build_jd_context(self, jd_model, project_id: str) -> str:
        jd = await jd_model.get_by_project_id(project_id)
        if not jd:
            raise ValueError(f"No job description found for project {project_id}")

        combined_text = (jd.description + (jd.prompt or "")).lower()
        if any(pattern in combined_text for pattern in INJECTION_PATTERNS):
            raise ValueError("Security Validation Failed: Potential prompt injection detected in Job Description or Prompt.")

        parts = [f"=== JOB DESCRIPTION ===\nTitle: {jd.title}\n\n{jd.description}"]
        if jd.prompt:
            parts.append(f"\nADDITIONAL SCREENING INSTRUCTIONS:\n{jd.prompt}")
        if jd.custom_rubric:
            parts.append(f"\nCUSTOM EVALUATION RUBRIC:\n{jd.custom_rubric}")
        if jd.weights:
            parts.append(f"\nSCORING WEIGHTS:\n{json.dumps(jd.weights)}")
        parts.append("\n=== END JOB DESCRIPTION ===")

        return "".join(parts)

    # ── Single CV Screening ──────────────────────────────────────────────

    async def screen_single_cv(
        self, generation_client, resume: Resume, jd_context: str, usage_controller=None, project_id: str = None
    ) -> dict:
        prompt = f"""{jd_context}

{SCREENING_SYSTEM_PROMPT}

Now analyze the following resume:

RESUME (file_id: {resume.file_id}):
{resume.full_content}

Return ONLY the JSON screening result."""

        try:
            response = await track_llm_call(
                generation_client=generation_client,
                prompt=prompt,
                config=SCREENING_GENERATION_CONFIG,
                usage_controller=usage_controller,
                project_id=project_id,
                file_id=resume.file_id,
                action_type="screening",
            )

            result = json.loads(response.content)
            return self._post_process_result(
                result, resume, generation_client.model_id,
                response.usage_metadata or {}
            )
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for CV {resume.id}: {e}")
            return self._build_error_result(resume, "Failed to parse LLM response")
        except Exception as e:
            logger.error(f"Screening error for CV {resume.id}: {e}")
            return self._build_error_result(resume, f"Screening failed: {str(e)}")

    # ── Keyword Extraction ───────────────────────────────────────────────

    async def extract_keywords_from_jd(self, generation_client, jd_text: str, usage_controller=None, project_id: str = None) -> list[str]:
        prompt = JD_KEYWORD_EXTRACTION_PROMPT.format(jd_text=jd_text[:2000])
        try:
            response = await track_llm_call(
                generation_client=generation_client,
                prompt=prompt,
                config=JSON_GENERATION_CONFIG,
                usage_controller=usage_controller,
                project_id=project_id,
                action_type="jd_extraction",
            )
            return json.loads(response.content)
        except Exception:
            return []

    # ── Light Screening ──────────────────────────────────────────────────

    def light_screen_cv(self, resume: Resume, score: float, jd_keywords: list[str]) -> dict:
        cv_text = resume.full_content.lower()
        matched = [kw for kw in jd_keywords if kw.lower() in cv_text]
        missing = [kw for kw in jd_keywords if kw.lower() not in cv_text]
        norm_score = int(min(score, 1.0) * 100)

        result = copy.deepcopy(LIGHT_RESULT_TEMPLATE)
        result.update({
            "fit_score": norm_score,
            "cv_id": str(resume.id),
            "candidate_name": resume.candidate_name,
            "contact_info": resume.contact_info,
            "key_match_analysis": {
                "strengths": matched,
                "missing_critical_skills": missing,
                "experience_analysis": LIGHT_RESULT_TEMPLATE["key_match_analysis"]["experience_analysis"]
            },
            "meta": {
                "method": "Light Screen (Keyword Match)",
                "model": "N/A",
                "tier": "Standard Tier"
            }
        })
        return result

    # ── Dynamic Split (1D Clustering) ────────────────────────────────────

    def _calculate_dynamic_split(self, scores: list[float], min_top_count: int) -> int:
        """
        Dynamically determines the split point using 1D clustering.
        Divides scores into 'High' and 'Low' clusters and returns the count of the High cluster.
        """
        n = len(scores)
        if n == 0:
            return 0
        if n < min_top_count:
            return n

        c1 = max(scores)  # High centroid
        c2 = min(scores)  # Low centroid

        if c1 - c2 < 0.05:
            return n if c1 > 0.7 else min_top_count

        cluster_split_idx = 0
        for _ in range(5):
            found_split = False
            for i, score in enumerate(scores):
                if abs(score - c2) < abs(score - c1):
                    cluster_split_idx = i
                    found_split = True
                    break

            if not found_split:
                cluster_split_idx = n

            high_cluster = scores[:cluster_split_idx]
            low_cluster = scores[cluster_split_idx:]

            new_c1 = sum(high_cluster) / len(high_cluster) if high_cluster else c1
            new_c2 = sum(low_cluster) / len(low_cluster) if low_cluster else c2

            if abs(new_c1 - c1) < 0.001 and abs(new_c2 - c2) < 0.001:
                break

            c1, c2 = new_c1, new_c2

        return max(min_top_count, cluster_split_idx)

    # ── Batch Screening (Full) ───────────────────────────────────────────

    async def screen_candidates(
        self,
        generation_client,
        resume_model,
        jd_model,
        project_id: str,
        file_ids: Optional[list[str]] = None,
        anonymize: bool = True,
        usage_controller=None
    ) -> list[dict]:
        jd_context = await self.build_jd_context(jd_model, project_id)
        resumes = await self._fetch_resumes(resume_model, project_id, file_ids)
        if not resumes:
            return []

        async def screen(cv):
            return await self.screen_single_cv(generation_client, cv, jd_context, usage_controller, project_id)

        results = await self._run_concurrent(screen, resumes)

        if anonymize:
            self._anonymize_results(results)
        return results

    # ── Smart Screening (Tiered) ─────────────────────────────────────────

    async def _process_bottom_tier(self, generation_client, resume_model, project_id, bottom_tier, jd_description, usage_controller):
        """Light-screen the bottom tier using keyword matching."""
        bottom_file_ids = [c["file_id"] for c in bottom_tier]
        bottom_resumes = await resume_model.get_resumes_by_file_ids(project_id, bottom_file_ids)
        jd_keywords = await self.extract_keywords_from_jd(generation_client, jd_description, usage_controller, project_id)

        resume_map = {r.file_id: r for r in bottom_resumes}
        return [
            self.light_screen_cv(resume_map[c["file_id"]], c["score"], jd_keywords)
            for c in bottom_tier
            if c["file_id"] in resume_map
        ]

    async def _process_top_tier(self, generation_client, resume_model, project_id, top_tier, jd_context, usage_controller):
        """Full LLM screen the top tier."""
        top_file_ids = [c["file_id"] for c in top_tier]
        top_resumes = await resume_model.get_resumes_by_file_ids(project_id, top_file_ids)

        async def screen(cv):
            return await self.screen_single_cv(generation_client, cv, jd_context, usage_controller, project_id)

        return await self._run_concurrent(screen, top_resumes)

    async def smart_screen_candidates(
        self,
        generation_client,
        resume_model,
        vector_controller,
        jd_model,
        project_model,
        project_id: str,
        file_ids: Optional[list[str]] = None,
        min_top_count: int = 5,
        anonymize: bool = True,
        usage_controller=None
    ) -> list[dict]:
        jd_context = await self.build_jd_context(jd_model, project_id)
        jd = await jd_model.get_by_project_id(project_id)

        project = await project_model.get_project_or_create_one(project_id)
        ranked_candidates = await vector_controller.search_and_aggregate(project, jd.description, k=1000)

        if file_ids:
            ranked_candidates = [c for c in ranked_candidates if c["file_id"] in file_ids]
        if not ranked_candidates:
            return []

        scores = [c["score"] for c in ranked_candidates]
        split_index = self._calculate_dynamic_split(scores, min_top_count)
        top_tier = ranked_candidates[:split_index]
        bottom_tier = ranked_candidates[split_index:]

        top_results = await self._process_top_tier(
            generation_client, resume_model, project_id, top_tier, jd_context, usage_controller
        )
        bottom_results = await self._process_bottom_tier(
            generation_client, resume_model, project_id, bottom_tier, jd.description, usage_controller
        )

        final_results = list(top_results) + bottom_results
        if anonymize:
            self._anonymize_results(final_results)
        return final_results

    # ── Streaming Variants ───────────────────────────────────────────────

    async def screen_candidates_stream(
        self,
        generation_client,
        resume_model,
        jd_model,
        project_id: str,
        file_ids: Optional[list[str]] = None,
        anonymize: bool = True,
        usage_controller=None
    ):
        jd_context = await self.build_jd_context(jd_model, project_id)
        resumes = await self._fetch_resumes(resume_model, project_id, file_ids)

        if not resumes:
            yield json.dumps({"signal": "complete", "processed": 0}) + "\n"
            return

        yield json.dumps({"signal": "meta", "total": len(resumes)}) + "\n"

        async def screen(cv):
            return await self.screen_single_cv(generation_client, cv, jd_context, usage_controller, project_id)

        pending = [screen(cv) for cv in resumes]
        for coro in asyncio.as_completed(pending):
            result = await coro
            if anonymize:
                self._anonymize_results([result])
            yield json.dumps(result) + "\n"

        yield json.dumps({"signal": "complete"}) + "\n"

    async def smart_screen_candidates_stream(
        self,
        generation_client,
        resume_model,
        vector_controller,
        jd_model,
        project_model,
        project_id: str,
        file_ids: Optional[list[str]] = None,
        min_top_count: int = 5,
        anonymize: bool = True,
        usage_controller=None
    ):
        jd_context = await self.build_jd_context(jd_model, project_id)
        jd = await jd_model.get_by_project_id(project_id)

        project = await project_model.get_project_or_create_one(project_id)
        ranked_candidates = await vector_controller.search_and_aggregate(project, jd.description, k=1000)

        if file_ids:
            ranked_candidates = [c for c in ranked_candidates if c["file_id"] in file_ids]
        if not ranked_candidates:
            yield json.dumps({"signal": "complete", "processed": 0}) + "\n"
            return

        scores = [c["score"] for c in ranked_candidates]
        split_index = self._calculate_dynamic_split(scores, min_top_count)
        top_tier = ranked_candidates[:split_index]
        bottom_tier = ranked_candidates[split_index:]

        yield json.dumps({
            "signal": "meta",
            "total": len(ranked_candidates),
            "top_tier_count": len(top_tier),
            "bottom_tier_count": len(bottom_tier)
        }) + "\n"

        # Stream bottom tier (light screen — instant)
        bottom_file_ids = [c["file_id"] for c in bottom_tier]
        bottom_resumes = await resume_model.get_resumes_by_file_ids(project_id, bottom_file_ids)
        jd_keywords = await self.extract_keywords_from_jd(generation_client, jd.description, usage_controller, project_id)
        resume_map = {r.file_id: r for r in bottom_resumes}

        for cand in bottom_tier:
            r = resume_map.get(cand["file_id"])
            if r:
                res = self.light_screen_cv(r, cand["score"], jd_keywords)
                if anonymize:
                    self._anonymize_results([res])
                yield json.dumps(res) + "\n"
                await asyncio.sleep(0)

        # Stream top tier (heavy LLM — as they complete)
        top_file_ids = [c["file_id"] for c in top_tier]
        top_resumes = await resume_model.get_resumes_by_file_ids(project_id, top_file_ids)

        if top_resumes:
            sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)

            async def screen(cv):
                async with sem:
                    return await self.screen_single_cv(generation_client, cv, jd_context, usage_controller, project_id)

            pending = [screen(cv) for cv in top_resumes]
            for coro in asyncio.as_completed(pending):
                result = await coro
                if anonymize:
                    self._anonymize_results([result])
                yield json.dumps(result) + "\n"

        yield json.dumps({"signal": "complete"}) + "\n"
