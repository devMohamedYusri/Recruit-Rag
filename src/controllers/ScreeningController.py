import json
import copy
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


class ScreeningController(BaseController):
    def __init__(self):
        super().__init__()

    async def build_jd_context(self, jd_model, project_id: str) -> str:
        jd = await jd_model.get_by_project_id(project_id)
        if not jd:
            raise ValueError(f"No job description found for project {project_id}")

        # Security Check: Detect prompt injection
        injection_patterns = ["ignore previous instructions", "system prompt", "you are now", "jailbreak"]
        combined_text = (jd.description + (jd.prompt or "")).lower()
        
        if any(pattern in combined_text for pattern in injection_patterns):
             raise ValueError("Security Validation Failed: Potential prompt injection detected in Job Description or Prompt.")

        jd_context = f"=== JOB DESCRIPTION ===\nTitle: {jd.title}\n\n{jd.description}"
        if jd.prompt:
            jd_context += f"\n\nADDITIONAL SCREENING INSTRUCTIONS:\n{jd.prompt}"
        
        if jd.custom_rubric:
            jd_context += f"\n\nCUSTOM EVALUATION RUBRIC:\n{jd.custom_rubric}"

        if jd.weights:
            jd_context += f"\n\nSCORING WEIGHTS:\n{json.dumps(jd.weights)}"
        jd_context += "\n=== END JOB DESCRIPTION ==="
        return jd_context

    async def screen_single_cv(
        self, generation_client, resume: Resume, jd_context: str, usage_controller=None, project_id: str=None
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
            # response is now LLMResponse
            result_text = response.content
            if usage_controller and project_id and response.usage_metadata:
                await usage_controller.log_usage(
                    project_id=project_id,
                    model_id=generation_client.model_id,
                    action_type="screening",
                    usage_metadata=response.usage_metadata
                )

            result = json.loads(result_text)
            
            result["meta"] = {
                "method": "LLM Screen",
                "model": generation_client.model_id,
                "usage": response.usage_metadata if response.usage_metadata else {}
            }
            
            # --- Post-Processing / Calibration ---
            
            # 1. Score Calibration: Avoid 0 for non-empty resumes
            if result.get("fit_score", 0) == 0 and len(resume.full_content.strip()) > 50:
                 result["fit_score"] = 5
            
            # 2. Interview Questions for Low Match
            if result.get("fit_score", 0) < 20:
                result["interview_prep"] = {
                    "interview_recommendation": "Not recommended for interview based on current resume evidence.",
                    "suggested_questions": []
                }
                
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
        anonymize: bool = True,
        usage_controller = None
    ) -> list[dict]:
        # Legacy/Fallback method (Full Screen for all)
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
                return await self.screen_single_cv(
                    generation_client, cv, jd_context, usage_controller, project_id
                )

        results = await asyncio.gather(*[safe_screen(cv) for cv in resumes])

        if anonymize:
            for result in results:
                result["candidate_name"] = "[REDACTED]"
                result["contact_info"] = {}

        return list(results)

    async def extract_keywords_from_jd(self, generation_client, jd_text: str, usage_controller=None, project_id: str=None) -> list[str]:
        prompt = f"""Extract 5-10 critical technical skills/keywords from this Job Description. 
        Return ONLY a JSON array of strings.
        JD: {jd_text[:2000]}"""
        try:
             response = await generation_client.generate(prompt=prompt, config={"response_mime_type": "application/json"})
             if usage_controller and project_id and response.usage_metadata:
                 await usage_controller.log_usage(
                     project_id=project_id,
                     model_id=generation_client.model_id,
                     action_type="jd_extraction",
                     usage_metadata=response.usage_metadata
                 )
             return json.loads(response.content)
        except Exception:
             return []

    def light_screen_cv(self, resume: Resume, score: float, jd_keywords: list[str]) -> dict:
        # Simple keyword matching (case-insensitive)
        cv_text = resume.full_content.lower()
        matched = [kw for kw in jd_keywords if kw.lower() in cv_text]
        missing = [kw for kw in jd_keywords if kw.lower() not in cv_text]
        
        # Normalize score to 0-100
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

    def _calculate_dynamic_split(self, scores: list[float], min_top_count: int) -> int:
        """
        Dynamically determines the split point using 1D clustering (Simplified K-Means).
        Divides scores into 'High' and 'Low' clusters and returns the count of the High cluster.
        """
        n = len(scores)
        if n == 0:
            return 0
        if n < min_top_count:
            return n

        # Initial centroids: max score (ideal High) and min score (ideal Low)
        # Using fixed points or percentile-based init can be more stable than random
        c1 = max(scores) # High centroid
        c2 = min(scores) # Low centroid
        
        # If all scores are very similar (variance is near zero), defaults depend on absolute value
        if c1 - c2 < 0.05:
            # If all are high (>0.7), take all. If all low, take min_top_count.
            return n if c1 > 0.7 else min_top_count

        # Simple 1D K-Means (2 iterations usually enough for convergence on 1D sorted data)
        for _ in range(5): 
            cluster_split_idx = 0
            
            # Find the split point where values switch from being closer to c1 to c2
            # Since scores are sorted descending, we just find the transition index
            found_split = False
            for i, score in enumerate(scores):
                dist_c1 = abs(score - c1)
                dist_c2 = abs(score - c2)
                
                if dist_c2 < dist_c1:
                    # Closer to Low centroid -> Limit of High cluster reached
                    cluster_split_idx = i
                    found_split = True
                    break
            
            if not found_split:
                 cluster_split_idx = n
            
            # Re-calculate centroids
            high_cluster = scores[:cluster_split_idx]
            low_cluster = scores[cluster_split_idx:]
            
            new_c1 = sum(high_cluster) / len(high_cluster) if high_cluster else c1
            new_c2 = sum(low_cluster) / len(low_cluster) if low_cluster else c2
            
            if abs(new_c1 - c1) < 0.001 and abs(new_c2 - c2) < 0.001:
                break # Converged
            
            c1, c2 = new_c1, new_c2

        # Ensure min safety floor
        return max(min_top_count, cluster_split_idx)

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
        usage_controller = None
    ) -> list[dict]:
        
        # 1. Get JD & Context
        jd_context = await self.build_jd_context(jd_model, project_id)
        jd = await jd_model.get_by_project_id(project_id)
        
        # 2. Hybrid Search & Rank
        project = await project_model.get_project_or_create_one(project_id)
        ranked_candidates = await vector_controller.search_and_aggregate(project, jd.description, k=1000)
        
        # Filter by file_ids if provided
        if file_ids:
            ranked_candidates = [c for c in ranked_candidates if c["file_id"] in file_ids]

        if not ranked_candidates:
            return []

        # 3. Dynamic Splitting (1D Clustering)
        # Extract scores
        scores = [c["score"] for c in ranked_candidates]
        
        # Determine split index dynamically
        split_index = self._calculate_dynamic_split(scores, min_top_count)
        
        # Apply Split
        top_tier = ranked_candidates[:split_index]
        bottom_tier = ranked_candidates[split_index:]

        # 4. Process Top Tier (Heavy LLM)
        top_file_ids = [c["file_id"] for c in top_tier]
        top_resumes = await resume_model.get_resumes_by_file_ids(project_id, top_file_ids)
        
        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)
        async def safe_screen_top(cv):
            async with sem:
                 return await self.screen_single_cv(generation_client, cv, jd_context, usage_controller, project_id)

        top_results = await asyncio.gather(*[safe_screen_top(cv) for cv in top_resumes])

        # 5. Process Bottom Tier (Light Screen)
        bottom_file_ids = [c["file_id"] for c in bottom_tier]
        bottom_resumes = await resume_model.get_resumes_by_file_ids(project_id, bottom_file_ids)
        
        # Extract keywords ONCE for light screen
        jd_keywords = await self.extract_keywords_from_jd(generation_client, jd.description, usage_controller, project_id)
        
        bottom_results = []
        resume_map = {r.file_id: r for r in bottom_resumes}
        
        for cand in bottom_tier:
            r = resume_map.get(cand["file_id"])
            if r:
                res = self.light_screen_cv(r, cand["score"], jd_keywords)
                bottom_results.append(res)
        
        final_results = top_results + bottom_results

        if anonymize:
            for result in final_results:
                result["candidate_name"] = "[REDACTED]"
                result["contact_info"] = {}
                
        return final_results
    async def screen_candidates_stream(
        self,
        generation_client,
        resume_model,
        jd_model,
        project_id: str,
        file_ids: Optional[list[str]] = None,
        anonymize: bool = True,
        usage_controller = None
    ):
        jd_context = await self.build_jd_context(jd_model, project_id)

        if file_ids:
            resumes = await resume_model.get_resumes_by_file_ids(project_id, file_ids)
        else:
            resumes = await resume_model.get_resumes_by_project_id(project_id)

        if not resumes:
            yield json.dumps({"signal": "complete", "processed": 0}) + "\n"
            return
            
        yield json.dumps({"signal": "meta", "total": len(resumes)}) + "\n"

        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)
        async def safe_screen(cv):
            async with sem:
                return await self.screen_single_cv(
                    generation_client, cv, jd_context, usage_controller, project_id
                )

        pending = [safe_screen(cv) for cv in resumes]
        for coro in asyncio.as_completed(pending):
            result = await coro
            if anonymize:
                result["candidate_name"] = "[REDACTED]"
                result["contact_info"] = {}
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
        usage_controller = None
    ):
        # 1. Get JD & Context
        jd_context = await self.build_jd_context(jd_model, project_id)
        jd = await jd_model.get_by_project_id(project_id)
        
        # 2. Hybrid Search & Rank
        project = await project_model.get_project_or_create_one(project_id)
        ranked_candidates = await vector_controller.search_and_aggregate(project, jd.description, k=1000)
        
        # Filter by file_ids if provided
        if file_ids:
            ranked_candidates = [c for c in ranked_candidates if c["file_id"] in file_ids]

        if not ranked_candidates:
            yield json.dumps({"signal": "complete", "processed": 0}) + "\n"
            return

        # 3. Dynamic Splitting (1D Clustering)
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

        # 4. Process Bottom Tier (Light Screen)
        bottom_file_ids = [c["file_id"] for c in bottom_tier]
        bottom_resumes = await resume_model.get_resumes_by_file_ids(project_id, bottom_file_ids)
        
        jd_keywords = await self.extract_keywords_from_jd(generation_client, jd.description, usage_controller, project_id)
        
        resume_map = {r.file_id: r for r in bottom_resumes}
        
        for cand in bottom_tier:
            r = resume_map.get(cand["file_id"])
            if r:
                res = self.light_screen_cv(r, cand["score"], jd_keywords)
                if anonymize:
                    res["candidate_name"] = "[REDACTED]"
                    res["contact_info"] = {}
                yield json.dumps(res) + "\n"
                await asyncio.sleep(0) # Yield control

        # 5. Process Top Tier (Heavy LLM) - Streaming as they complete!
        top_file_ids = [c["file_id"] for c in top_tier]
        top_resumes = await resume_model.get_resumes_by_file_ids(project_id, top_file_ids)
        
        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)
        async def safe_screen_top(cv):
            async with sem:
                 return await self.screen_single_cv(generation_client, cv, jd_context, usage_controller, project_id)

        if top_resumes:
            pending = [safe_screen_top(cv) for cv in top_resumes]
            for coro in asyncio.as_completed(pending):
                result = await coro
                if anonymize:
                    result["candidate_name"] = "[REDACTED]"
                    result["contact_info"] = {}
                yield json.dumps(result) + "\n"
            
        yield json.dumps({"signal": "complete"}) + "\n"
