import re
import json
import copy
import math
import asyncio
import logging
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from langsmith import traceable
from .BaseController import BaseController
from models.DB_schemas.resume import Resume
from utils.prompts import SCREENING_SYSTEM_PROMPT, JD_KEYWORD_EXTRACTION_PROMPT

class JDKeywordsResponse(BaseModel):
    primary_domain: str = "Unknown"
    domain_synonyms: List[str] = Field(default_factory=list)
    seniority_level: str = "Unknown"
    must_have_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    implicit_requirements: List[str] = Field(default_factory=list)
    required_years_experience: Any = 0.0
from utils.constants import (
    ERROR_RESULT_TEMPLATE,
    LIGHT_RESULT_TEMPLATE,
    SCREENING_GENERATION_CONFIG,
    JSON_GENERATION_CONFIG,
    INJECTION_PATTERNS,
    SCORING_VERSION,
    FEATURE_VERSION
)
from utils.helpers import track_llm_call, _fire_and_forget
from utils.date_parser import calculate_total_experience

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
    def _post_process_result(result: dict, resume: Resume, model_id: str, usage: dict, method: str = "LLM Screen", required_years: float = 0.0) -> dict:
        """Calibrate scores, attach metadata, and inject candidate fields."""
        result["meta"] = {
            "method": method,
            "model": model_id,
            "usage": usage,
        }

        # Score Calibration: Avoid 0 for non-empty resumes
        if result.get("fit_score", 0) == 0 and len(getattr(resume, "full_content", " " * 51).strip()) > 50:
            result["fit_score"] = 5

        # Handle interview questions - prioritize LLM generated ones
        if not result.get("interview_prep"):
             result["interview_prep"] = {
                 "interview_recommendation": "Calculated Fit: High Match" if result.get("fit_score", 0) >= 30 else "Calculated Fit: Under Benchmarks",
                 "suggested_questions": ["Can you tell me more about your experience mentioned in your summary?"]
             }
        elif not result["interview_prep"].get("suggested_questions"):
             result["interview_prep"]["suggested_questions"] = ["Can you tell me more about your experience mentioned in your summary?"]

        # Use relevant experience years if available
        exp_years = result.get("scoring_breakdown", {}).get("relevant_experience_years", 
                        result.get("scoring_breakdown", {}).get("experience_ratio", 0) * 10)

        # Calculate seniority label from experience
        if exp_years < 1.0: seniority = "Entry Level"
        elif exp_years < 3.0: seniority = "Junior"
        elif exp_years < 6.0: seniority = "Mid-Level"
        elif exp_years < 10.0: seniority = "Senior"
        else: seniority = "Expert / Lead"

        # SHAPE MATCHING: Map flattened fields to nested frontend expectations
        result["key_match_analysis"] = {
            "strengths": result.pop("strengths", []),
            "missing_critical_skills": result.pop("gaps", []),
            "experience_analysis": {
                "total_relevant_experience_years": exp_years,
                "required_years": required_years,
                "seniority_level": seniority,
                "seniority_alignment": "Exceeds Requirements" if exp_years > required_years + 2 else ("Meets Requirements" if exp_years >= required_years else "Under-qualified"),
                "role_fit_justification": result.get("reason", "")
            }
        }
        
        result["flags"] = {
            "red_flags": result.pop("red_flags", []),
            "yellow_flags": result.pop("yellow_flags", [])
        }

        result["cv_id"] = str(resume.id) if hasattr(resume, "id") else getattr(resume, "cv_id", "unknown")
        result["candidate_name"] = getattr(resume, "candidate_name", "Unknown Candidate")
        result["contact_info"] = getattr(resume, "contact_info", {})
        return result

    @staticmethod
    def _anonymize_results(results) -> None:
        """Redact PII from a list of screening results (in-place)."""
        for result in results:
            result["candidate_name"] = "[REDACTED]"
            result["contact_info"] = {}

    async def _fetch_resumes(self, resume_model, project_id: str, user_id: object, file_ids: Optional[list[str]] = None) -> list:
        logger.info(f"Fetching resumes for project {project_id}: user={user_id}, file_ids={file_ids}")
        if file_ids:
            res = await resume_model.get_resumes_by_file_ids(project_id, user_id, file_ids)
        else:
            res = await resume_model.get_resumes_by_project_id(project_id, user_id)
        logger.info(f"Fetch complete. Found {len(res)} resumes in database.")
        return res

    async def _run_concurrent(self, fn, items: list) -> list:
        """Run an async function over items with a concurrency semaphore."""
        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)

        async def limited(item):
            async with sem:
                return await fn(item)

        return list(await asyncio.gather(*[limited(item) for item in items]))

    # ── JD Context ───────────────────────────────────────────────────────

    async def build_jd_context(self, jd_model, project_id: str, user_id: object) -> str:
        from datetime import datetime
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        jd = await jd_model.get_by_project_id(project_id, user_id)
        if not jd:
            raise ValueError(f"No job description found for project {project_id}")

        combined_text = (jd.description + (jd.prompt or "")).lower()
        if any(pattern in combined_text for pattern in INJECTION_PATTERNS):
            raise ValueError("Security Validation Failed: Potential prompt injection detected in Job Description or Prompt.")

        parts = [ f"Current Date: {current_date_str}\n\n=== JOB DESCRIPTION ===\nTitle: {jd.title}\n\n{jd.description}" ]
        if jd.prompt:
            parts.append(f"\nADDITIONAL SCREENING INSTRUCTIONS:\n{jd.prompt}")
        if jd.custom_rubric:
            parts.append(f"\nCUSTOM EVALUATION RUBRIC:\n{jd.custom_rubric}")
        if jd.weights:
            parts.append(f"\nSCORING WEIGHTS:\n{json.dumps(jd.weights)}")
        parts.append("\n=== END JOB DESCRIPTION ===")

        return "".join(parts)

    # ── Single CV Screening ──────────────────────────────────────────────

    # ── Phase 1 Mathematical Base Scoring ─────────────────────────────────────

    def _calculate_phase1_math(self, resume: Resume, jd_parsed: dict) -> dict:
        """Deterministic Phase 1 scoring (Feature Extraction)"""
        cv_text = resume.full_content.lower()
        
        # Support both legacy array fallback and new dict schema
        must_haves = jd_parsed.get("must_have_skills", []) if isinstance(jd_parsed, dict) else jd_parsed
        nice_to_haves = jd_parsed.get("nice_to_have_skills", []) if isinstance(jd_parsed, dict) else []
        jd_domain_synonyms = jd_parsed.get("domain_synonyms", []) if isinstance(jd_parsed, dict) else []
        
        must_haves_lower = [str(k).lower() for k in must_haves if k]
        nice_haves_lower = [str(k).lower() for k in nice_to_haves]
        
        # 1. req_kw_ratio: Must-have keyword strict checking
        must_have_len = max(len(must_haves_lower), 1)
        matched_must_haves = [kw for kw in must_haves_lower if kw in cv_text]
        missing_must_haves = [kw for kw in must_haves_lower if kw not in cv_text]
        req_kw_ratio = min(len(matched_must_haves) / must_have_len, 1.0)
        
        # 2. skill_overlap: Both must and nice-to-have matches vs parsed skills
        # Null-safe skill extraction
        raw_skills = resume.parsed_data.get("skills")
        if not isinstance(raw_skills, list):
            parsed_skills = []
        else:
            parsed_skills = [str(s).lower() for s in raw_skills if s]
        
        matched_nice_haves = [kw for kw in nice_haves_lower if any(kw in ps or ps in kw for ps in parsed_skills) or kw in cv_text]
        missing_nice_haves = [kw for kw in nice_haves_lower if kw not in matched_nice_haves]
        
        skill_must_matches = sum(1 for ps in parsed_skills if any(kw in ps or ps in kw for kw in must_haves_lower))
        skill_nice_matches = len(matched_nice_haves)
        
        total_jd_skills = max(len(must_haves_lower) + len(nice_haves_lower), 1)
        skill_overlap = min((skill_must_matches * 1.5 + skill_nice_matches) / total_jd_skills, 1.0)
        
        # 3. exp_ratio: Domain-filtered and recency-weighted total years
        from utils.date_parser import calculate_relevant_experience, calculate_total_experience
        from utils.domain_resolver import resolve_domain
        jd_domain_synonyms = jd_parsed.get("domain_synonyms", [])
        
        work_hist = resume.parsed_data.get("work_history", [])
        if not isinstance(work_hist, list):
            work_hist = []
        else:
            work_hist = [j for j in work_hist if isinstance(j, dict)]

        domain_match = True
        recent_jobs = work_hist[:2]
        if jd_domain_synonyms and recent_jobs:
             domain_match = any(resolve_domain(job.get("industry_domain", "Unknown"), jd_domain_synonyms) for job in recent_jobs)
        
        domain_penalty = 1.0 if domain_match else 0.8
        
        # Calculate total and relevant exp
        raw_total_exp = calculate_total_experience(work_hist)
        total_relevant_exp = calculate_relevant_experience(work_hist, jd_domain_synonyms) if jd_domain_synonyms else raw_total_exp
        
        required_years = float(jd_parsed.get("required_years_experience", 0.0))
        benchmark_years = max(required_years, 1.0) # Assume at least 1 year fallback
        
        exp_score = min(total_relevant_exp / benchmark_years, 1.0)
        
        # 4. edu_match
        edu_match = 1.0 if resume.parsed_data.get("education") else 0.5
        
        # 4. Final Aggregation
        # Weighted aggregate: Skills (40%), Exp (40%), JD Keywords (15%), Edu (5%)
        base_score = (0.4 * skill_overlap + 0.4 * exp_score + 0.15 * req_kw_ratio + 0.05 * edu_match) * 100
        base_score = base_score * domain_penalty
        
        return {
            "base_score": round(max(5, base_score), 1),
            "relevant_experience_years": round(total_relevant_exp, 1),
            "skill_overlap": round(skill_overlap, 2),
            "required_years": required_years,
            "domain_match": domain_match,
            "required_keywords_ratio": round(req_kw_ratio, 4),
            "education_match": round(edu_match, 4),
            "matched_must_haves": matched_must_haves,
            "missing_must_haves": missing_must_haves,
            "matched_nice_haves": matched_nice_haves,
            "missing_nice_haves": missing_nice_haves
        }

    # ── JSON Repair Helper ────────────────────────────────────────────────

    @staticmethod
    def _extract_json_text(raw: str) -> str:
        """Strip markdown fences and surrounding prose from LLM output."""
        text = raw.strip()
        # Remove ```json ... ``` or ``` ... ```
        if "```json" in text:
            text = text.split("```json", 1)[-1]
            if "```" in text:
                text = text.rsplit("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[-1]
            if "```" in text:
                text = text.rsplit("```", 1)[0]
        return text.strip()

    @staticmethod
    def _repair_json(text: str) -> str:
        """
        Best-effort repair of common LLM JSON errors:
        1. Trailing commas before ] or }
        2. Unterminated strings (close them)
        3. Unbalanced brackets (close them)
        """
        # 1. Remove trailing commas: ,] or ,}
        text = re.sub(r',\s*([}\]])', r'\1', text)

        # 2. Replace literal unescaped newlines inside strings with \\n
        #    Walk char-by-char inside string boundaries
        result = []
        in_string = False
        escape_next = False
        for ch in text:
            if escape_next:
                result.append(ch)
                escape_next = False
                continue
            if ch == '\\' and in_string:
                result.append(ch)
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string and ch == '\n':
                result.append('\\n')
                continue
            result.append(ch)

        # If still inside a string at EOF, close it
        if in_string:
            result.append('"')
        text = ''.join(result)

        # 3. Balance brackets / braces
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        text += ']' * max(0, open_brackets)
        text += '}' * max(0, open_braces)

        return text

    # ── Single CV Screening (Phase 2 LLM) ───────────────────────────────────
    @traceable(name="screen_single_cv")
    async def screen_single_cv(
        self, generation_client, resume: Resume, jd_context: str, phase1_data: dict, user_id: object, usage_controller=None, project_id: str = None
    ) -> dict:
        from models.DB_schemas.screening import LLMScreeningResponse, ScreeningResult
        import json
        
        schema_json = json.dumps(LLMScreeningResponse.model_json_schema(), indent=2)
        
        prompt = f"""{jd_context}

{SCREENING_SYSTEM_PROMPT}

You MUST return a JSON object that strictly adheres to the following JSON schema:
{schema_json}

CRITICAL RULES:
- Return ONLY valid JSON. No markdown, no explanation, no extra text.
- Every string value must be properly closed with a quote.
- Keep string values concise (under 200 characters each) to avoid truncation.

Now analyze the following resume:

RESUME (file_id: {resume.file_id}):
{resume.full_content[:3000]}

Return ONLY the JSON screening result."""

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await track_llm_call(
                    generation_client=generation_client,
                    prompt=prompt,
                    config=SCREENING_GENERATION_CONFIG,
                    usage_controller=usage_controller,
                    user_id=user_id,
                    project_id=project_id,
                    file_id=resume.file_id,
                    action_type="screening",
                )

                raw_content = response.content.strip()
                content = self._extract_json_text(raw_content)
                
                result_dict = None
                # Attempt 1: Direct parse
                try:
                    result_dict = json.loads(content, strict=False)
                except json.JSONDecodeError:
                    pass
                
                # Attempt 2: Repair and parse
                if result_dict is None:
                    try:
                        repaired = self._repair_json(content)
                        result_dict = json.loads(repaired, strict=False)
                        logger.info(f"JSON repair succeeded for CV {resume.id}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON repair failed for CV {resume.id}: {e}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            raise e

                # Rescue arrays/strings if the LLM hallucinates a deeply nested or legacy schema
                def _flatten_rescue(d: dict, target: dict):
                    for k, v in d.items():
                        k_lower = k.lower()
                        # Do NOT flatten these specific structured fields
                        if k_lower in ["interview_prep", "contact_info"]:
                            target[k] = v
                            continue
                            
                        if isinstance(v, dict):
                            _flatten_rescue(v, target)
                        else:
                            if k_lower in ["missing_critical_skills", "missing_skills", "gaps"]:
                                target["gaps"] = v
                            elif k_lower in ["core_match_strengths", "strengths"]:
                                target["strengths"] = v
                            elif k_lower in ["executive_summary", "summary"]:
                                target["summary"] = v
                            elif k_lower in ["role_fit_justification", "justification", "reason", "fit_justification"]:
                                target["reason"] = v
                            elif k_lower in ["red_flags", "serious_concerns", "risk_flags"]:
                                target["red_flags"] = v
                            elif k_lower in ["yellow_flags", "minor_concerns", "attention_markers"]:
                                target["yellow_flags"] = v
                            elif k not in target:
                                target[k] = v

                flat_dict = {}
                _flatten_rescue(result_dict, flat_dict)
                result_dict = flat_dict

                # Validate LLM output bounds (-10 to 10)
                validated_llm = LLMScreeningResponse(**result_dict)
                llm_data = validated_llm.model_dump()
                
                # Compute deterministic float Final Score
                adjustment = llm_data["adjustment"]
                final_score = round(max(0, min(100, phase1_data["base_score"] + adjustment)), 2)
                
                # Translate final score to label
                if final_score < 30: label = "Low Match"
                elif final_score < 60: label = "Medium Match"
                elif final_score < 85: label = "High Match"
                else: label = "Excellent Match"
                
                # Build complete ScreeningResult
                final_result = ScreeningResult(
                    fit_score=final_score,
                    fit_label=label,
                    scoring_breakdown=phase1_data,
                    adjustment=adjustment,
                    reason=llm_data["reason"],
                    executive_summary=llm_data["summary"],
                    strengths=llm_data.get("strengths", []),
                    gaps=llm_data.get("gaps", []),
                    red_flags=llm_data.get("red_flags", []),
                    yellow_flags=llm_data.get("yellow_flags", []),
                    risk_flags=llm_data.get("red_flags", []) + llm_data.get("yellow_flags", []),
                    interview_prep=llm_data.get("interview_prep", {})
                ).model_dump()

                return self._post_process_result(
                    final_result, resume, generation_client.model_id,
                    response.usage_metadata or {},
                    required_years=phase1_data.get("required_years", 0.0)
                )
            except Exception as e:
                logger.error(f"Screening error for CV {resume.id}: {e}")
                if attempt < max_retries - 1: continue
                return self._build_error_result(resume, f"Screening failed: {str(e)}")

    # ── Keyword Extraction ───────────────────────────────────────────────
    @traceable(name="extract_keywords_from_jd")
    async def extract_keywords_from_jd(self, generation_client, jd_text: str, user_id: object, usage_controller=None, project_id: str = None) -> dict:
        from datetime import datetime
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        prompt = f"Current Date: {current_date_str}\n\n" + JD_KEYWORD_EXTRACTION_PROMPT.format(jd_text=jd_text[:2000])
        try:
            response = await track_llm_call(
                generation_client=generation_client,
                prompt=prompt,
                config=JSON_GENERATION_CONFIG,
                usage_controller=usage_controller,
                user_id=user_id,
                project_id=project_id,
                action_type="jd_extraction",
            )
            raw_text = self._extract_json_text(response.content)
            repaired = self._repair_json(raw_text)
            parsed = json.loads(repaired, strict=False)
            
            # Use JDKeywordsResponse to validate and provide defaults for missing keys
            validated = JDKeywordsResponse(**parsed)
            # Extract years from Any (might be string like "4+")
            rye = validated.required_years_experience
            if isinstance(rye, str):
                match = re.search(r'(\d+)', rye)
                validated.required_years_experience = float(match.group(1)) if match else 0.0
            
            return validated.model_dump()
        except Exception as e:
            logger.warning(f"JD parsed keyword extraction failed: {e}. Returning fallback schema.")
            return JDKeywordsResponse().model_dump()

    # ── Light Screening ──────────────────────────────────────────────────

    def light_screen_cv(self, resume: Resume, phase1_data: dict) -> dict:
        """Phase 1 bottom 70% gets no LLM adjustment."""
        from models.DB_schemas.screening import ScreeningResult
        
        base_score = phase1_data["base_score"]
        final_score = round(base_score, 2)
        
        if final_score < 30: label = "Low Match"
        elif final_score < 60: label = "Medium Match"
        elif final_score < 85: label = "High Match"
        else: label = "Excellent Match"
        
        strengths = [f"Matched Keyword: {kw}" for kw in phase1_data.get("matched_must_haves", []) + phase1_data.get("matched_nice_haves", [])]
        gaps = [f"Missing Must-Have: {kw}" for kw in phase1_data.get("missing_must_haves", [])]
        
        if phase1_data.get("relevant_experience_years", 0) > 0:
            strengths.append(f"Found {round(phase1_data['relevant_experience_years'], 1)}y relevant experience")
        else:
            gaps.append("Minimal domain-relevant experience detected")
            
        summary_parts = ["Processed via keyword and experience matching."]
        overlap = phase1_data.get("skill_overlap", 0)
        if overlap > 0.6: summary_parts.append("Strong technical keyword overlap.")
        elif overlap < 0.2: summary_parts.append("Very weak keyword overlap.")
        
        result = ScreeningResult(
            fit_score=final_score,
            fit_label=label,
            scoring_breakdown=phase1_data,
            adjustment=0,
            reason="Bottom tier deterministic screen. No LLM adjustment allotted.",
            executive_summary=" ".join(summary_parts),
            strengths=strengths[:5],
            gaps=gaps[:5]
        ).model_dump()

        result = self._post_process_result(
            result, resume, "N/A", {}, 
            method="Light Screen (Keyword Match)",
            required_years=phase1_data.get("required_years", 0.0)
        )
        result["meta"]["tier"] = "Standard Tier"
        
        return result

    # ── Pre- and Post-Processing ─────────────────────────────────────────

    def _apply_hard_filter(self, resumes: list[Resume], jd_parsed: dict) -> tuple[list[Resume], list[dict]]:
        """DEPRECATED: Hard exclusion removed in favor of soft Phase 1 penalties."""
        return resumes, []

    def _normalize_batch_scores(self, final_results: list[dict]):
        if not final_results: return
        
        valid_scores = [r.get("fit_score", 0) for r in final_results if r.get("meta", {}).get("method") != "Hard Filter"]
        if not valid_scores: return
        
        max_score = max(valid_scores)
        if max_score <= 0: return
        
        scale_factor = 95.0 / max_score
        
        for r in final_results:
            if r.get("meta", {}).get("method") == "Hard Filter":
                continue 
                
            raw = r.get("fit_score", 0)
            scaled = raw * scale_factor
            score = round(max(scaled, 15.0), 2)
            r["fit_score"] = score
            
            if score < 30: label = "Low Match"
            elif score < 60: label = "Medium Match"
            elif score < 85: label = "High Match"
            else: label = "Excellent Match"
            r["fit_label"] = label
            
    # ── Batch Screening (Full) ───────────────────────────────────────────
    @traceable(name="screen_candidates")
    async def screen_candidates(
        self,
        generation_client,
        resume_model,
        jd_model,
        project_id: str,
        user_id: object,
        file_ids: Optional[list[str]] = None,
        anonymize: bool = True,
        usage_controller=None,
        screening_result_model=None
    ) -> list[dict]:
        jd_context = await self.build_jd_context(jd_model, project_id, user_id)
        jd = await jd_model.get_by_project_id(project_id, user_id)
        resumes = await self._fetch_resumes(resume_model, project_id, user_id, file_ids)
        if not resumes:
            return []
            
        jd_keywords = await self.extract_keywords_from_jd(generation_client, jd.description, user_id, usage_controller, project_id)
        passed_resumes, rejected_results = self._apply_hard_filter(resumes, jd_keywords)

        async def screen(cv):
            phase1 = self._calculate_phase1_math(cv, jd_keywords)
            result = await self.screen_single_cv(generation_client, cv, jd_context, phase1, user_id, usage_controller, project_id)
            return result

        results = await self._run_concurrent(screen, passed_resumes)
        final_results = results + rejected_results
        
        self._normalize_batch_scores(final_results)
        
        # Save to DB after normalization
        if screening_result_model:
            from models.DB_schemas.screening_result import ScreeningResultDB
            results_to_db = []
            for res in final_results:
                try:
                    cv_id = res.get("cv_id") or res.get("file_id")
                    results_to_db.append(ScreeningResultDB(
                        project_id=project_id,
                        user_id=user_id,
                        file_id=cv_id,
                        result=res
                    ))
                except Exception as e:
                    logger.error(f"Failed to save screening result for {cv_id}: {e}")
            if results_to_db:
                 _fire_and_forget(screening_result_model.create_screening_results_bulk(results_to_db))

        if anonymize:
            self._anonymize_results(final_results)
        return final_results

    # ── Smart Screening (Tiered Deterministic) ─────────────────────────────────────────

    async def _process_bottom_tier(self, bottom_tier_tuples) -> list[dict]:
        """Light-screen the bottom tier."""
        return [
            self.light_screen_cv(resume, phase1)
            for resume, phase1 in bottom_tier_tuples
        ]

    async def _process_top_tier(self, generation_client, top_tier_tuples, jd_context, project_id, user_id, usage_controller):
        """Full LLM Phase 2 screen the top tier."""
        async def screen(tup):
            resume, phase1 = tup
            return await self.screen_single_cv(generation_client, resume, jd_context, phase1, user_id, usage_controller, project_id)

        return await self._run_concurrent(screen, top_tier_tuples)

    @traceable(name="smart_screen_candidates")
    async def smart_screen_candidates(
        self,
        generation_client,
        resume_model,
        vector_controller, # Left for interface conformity but unused
        jd_model,
        project_model,
        project_id: str,
        user_id: object,
        file_ids: Optional[list[str]] = None,
        min_top_count: int = 5,
        anonymize: bool = True,
        usage_controller=None,
        screening_result_model=None,
        ratio_config: dict = None
    ) -> list[dict]:
        jd_context = await self.build_jd_context(jd_model, project_id, user_id)
        jd = await jd_model.get_by_project_id(project_id, user_id)

        project = await project_model.get_project_by_id(project_id, user_id)
        if not project:
            return []
            
        resumes = await self._fetch_resumes(resume_model, project_id, user_id, file_ids)
        if not resumes:
            return []

        jd_keywords = await self.extract_keywords_from_jd(generation_client, jd.description, user_id, usage_controller, project_id)
        passed_resumes, rejected_results = self._apply_hard_filter(resumes, jd_keywords)

        # Phase 1: Mathematical Base Scoring for ALL passed resumes (Parallelized CPU work)
        async def _score_math(r):
            # _calculate_phase1_math can be CPU-heavy due to date parsing in experience calculation
            p1 = await asyncio.to_thread(self._calculate_phase1_math, r, jd_keywords)
            return (r, p1)
            
        scored_tuples = await asyncio.gather(*[_score_math(r) for r in passed_resumes])
            
        # Tie-Breaker Sort! `-base_score` + `resume_hash`
        scored_tuples.sort(key=lambda x: (-x[1]["base_score"], x[0].resume_hash or str(x[0].id)))

        # Slicing Determinism (Strict 30%)
        top_k = math.ceil(0.30 * len(scored_tuples))
        top_tier = scored_tuples[:top_k]
        bottom_tier = scored_tuples[top_k:]

        top_results = await self._process_top_tier(
            generation_client, top_tier, jd_context, project_id, user_id, usage_controller
        )
        
        bottom_results = await self._process_bottom_tier(bottom_tier)
        
        final_results = top_results + bottom_results + rejected_results
        
        # Gap 4: Normalization
        self._normalize_batch_scores(final_results)
        
        final_results.sort(key=lambda x: (-x.get("fit_score", 0), x.get("cv_id", "")))

        # Save all results to DB (Bulk)
        if screening_result_model and final_results:
            from models.DB_schemas.screening_result import ScreeningResultDB
            results_to_db = []
            for res in final_results:
                try:
                    # Find original resume for hash
                    resume = next((r for r in resumes if str(r.id) == res["cv_id"]), None)
                    results_to_db.append(ScreeningResultDB(
                        project_id=project_id,
                        user_id=user_id,
                        file_id=res["cv_id"],
                        resume_hash=resume.resume_hash if resume else res["cv_id"],
                        scoring_version=SCORING_VERSION,
                        feature_version=FEATURE_VERSION,
                        base_score=res.get("scoring_breakdown", {}).get("base_score"),
                        adjustment=res.get("adjustment", 0),
                        final_score=res.get("fit_score"),
                        result=res
                    ))
                except Exception as e:
                    logger.error(f"Failed to prepare screening result for {res.get('cv_id')}: {e}")
            
            if results_to_db:
                _fire_and_forget(screening_result_model.create_screening_results_bulk(results_to_db))

        if anonymize:
            self._anonymize_results(final_results)
        return final_results

    # ── Streaming Variants ───────────────────────────────────────────────

    @traceable(name="screen_candidates_stream")
    async def screen_candidates_stream(
        self,
        generation_client,
        resume_model,
        jd_model,
        project_id: str,
        user_id: object,
        file_ids: Optional[list[str]] = None,
        anonymize: bool = True,
        usage_controller=None,
        screening_result_model=None
    ):
        jd_context = await self.build_jd_context(jd_model, project_id, user_id)
        resumes = await self._fetch_resumes(resume_model, project_id, user_id, file_ids)

        if not resumes:
            yield json.dumps({"signal": "complete", "processed": 0}) + "\n"
            return

        yield json.dumps({"signal": "meta", "total": len(resumes)}) + "\n"

        async def screen(cv):
            jd_keywords = ["general"]
            phase1 = self._calculate_phase1_math(cv, jd_keywords)
            return await self.screen_single_cv(generation_client, cv, jd_context, phase1, user_id, usage_controller, project_id)

        pending = [screen(cv) for cv in resumes]
        for coro in asyncio.as_completed(pending):
            result = await coro
            if screening_result_model:
                try:
                    from models.DB_schemas.screening_result import ScreeningResultDB
                    _fire_and_forget(screening_result_model.create_screening_result(ScreeningResultDB(
                        project_id=project_id,
                        user_id=user_id,
                        file_id=result.get("cv_id") or result.get("file_id"),
                        result=result
                    )))
                except Exception as e:
                    logger.error(f"Failed to save screening result for {result['cv_id']}: {e}")
            if anonymize:
                self._anonymize_results([result])
            yield json.dumps(result) + "\n"

        yield json.dumps({"signal": "complete"}) + "\n"

    @traceable(name="smart_screen_candidates_stream")
    async def smart_screen_candidates_stream(
        self,
        generation_client,
        resume_model,
        vector_controller, # Unused 
        jd_model,
        project_model,
        project_id: str,
        user_id: object,
        file_ids: Optional[list[str]] = None,
        min_top_count: int = 5,
        anonymize: bool = True,
        usage_controller=None,
        screening_result_model=None,
        ratio_config: dict = None
    ):
        try:
            jd_context = await self.build_jd_context(jd_model, project_id, user_id)
            jd = await jd_model.get_by_project_id(project_id, user_id)

            project = await project_model.get_project_by_id(project_id, user_id)
            if not project:
                yield json.dumps({"signal": "complete", "processed": 0}) + "\n"
                return
                
            resumes = await self._fetch_resumes(resume_model, project_id, user_id, file_ids)
            if not resumes:
                yield json.dumps({"signal": "complete", "processed": 0}) + "\n"
                return

            jd_keywords = await self.extract_keywords_from_jd(generation_client, jd.description, user_id, usage_controller, project_id)
            passed_resumes, rejected_results = self._apply_hard_filter(resumes, jd_keywords)

            yield json.dumps({
                "signal": "meta",
                "total": len(resumes),
                "passed_count": len(passed_resumes),
                "rejected_count": len(rejected_results)
            }) + "\n"

            # 1. Yield rejected results immediately
            for rej in rejected_results:
                if screening_result_model:
                    try:
                        from models.DB_schemas.screening_result import ScreeningResultDB
                        # Ensure we have a valid cv_id
                        cv_id = rej.get("cv_id") or "rejected"
                        _fire_and_forget(screening_result_model.create_screening_result(ScreeningResultDB(
                            project_id=project_id,
                            user_id=user_id,
                            file_id=cv_id,
                            result=rej
                        )))
                    except Exception as e:
                        logger.error(f"Failed to save rejected result in stream: {e}")
                
                if anonymize:
                    self._anonymize_results([rej])
                yield json.dumps(rej) + "\n"

            # 2. Score passed resumes (Parallelized to avoid event loop blocking)
            async def _score_task(r):
                try:
                    # Offload potentially heavy regex work to thread
                    p1 = await asyncio.to_thread(self._calculate_phase1_math, r, jd_keywords)
                    return (r, p1)
                except Exception as e:
                    logger.error(f"Scoring error for {r.id}: {e}")
                    return (r, None)

            tasks = [_score_task(r) for r in passed_resumes]
            scored_results = await asyncio.gather(*tasks)
            scored_tuples = [t for t in scored_results if t[1] is not None]
            
            # Tie-Breaker Sort! `-base_score` + `resume_hash`
            scored_tuples.sort(key=lambda x: (-x[1]["base_score"], x[0].resume_hash or str(x[0].id)))

            top_k = math.ceil(0.30 * len(scored_tuples))
            top_tier = scored_tuples[:top_k]
            bottom_tier = scored_tuples[top_k:]

            logger.info(f"Smart screen stream split for project {project_id}: total_passed={len(scored_tuples)}, top={len(top_tier)}, bottom={len(bottom_tier)}")

            # Stream bottom tier
            for resume, phase1 in bottom_tier:
                try:
                    res = self.light_screen_cv(resume, phase1)
                    if screening_result_model:
                        from models.DB_schemas.screening_result import ScreeningResultDB
                        _fire_and_forget(screening_result_model.create_screening_result(ScreeningResultDB(
                            project_id=project_id,
                            user_id=user_id,
                            file_id=res["cv_id"],
                            resume_hash=resume.resume_hash,
                            scoring_version=SCORING_VERSION,
                            feature_version=FEATURE_VERSION,
                            base_score=phase1["base_score"],
                            adjustment=0,
                            final_score=res["fit_score"],
                            result=res
                        )))
                    if anonymize:
                        self._anonymize_results([res])
                    yield json.dumps(res) + "\n"
                except Exception as e:
                    logger.error(f"Error yielding light screen result for {resume.id}: {e}")
                await asyncio.sleep(0)

            # Stream top tier
            if top_tier:
                sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)

                async def screen(tup):
                    resume, phase1 = tup
                    async with sem:
                        return await self.screen_single_cv(generation_client, resume, jd_context, phase1, user_id, usage_controller, project_id)

                pending = [screen(tup) for tup in top_tier]
                for coro in asyncio.as_completed(pending):
                    result = await coro
                    if screening_result_model:
                        try:
                            resume = next(r for r, _ in top_tier if str(r.id) == result["cv_id"])
                            from models.DB_schemas.screening_result import ScreeningResultDB
                            _fire_and_forget(screening_result_model.create_screening_result(ScreeningResultDB(
                                project_id=project_id,
                                user_id=user_id,
                                file_id=result["cv_id"],
                                resume_hash=resume.resume_hash,
                                scoring_version=SCORING_VERSION,
                                feature_version=FEATURE_VERSION,
                                base_score=result.get("scoring_breakdown", {}).get("base_score"),
                                adjustment=result.get("adjustment", 0),
                                final_score=result.get("fit_score", 0),
                                result=result
                            )))
                        except Exception as e:
                            logger.error(f"Failed to save smart screening stream result for {result['cv_id']}: {e}")
                    if anonymize:
                        self._anonymize_results([result])
                    try:
                        yield json.dumps(result) + "\n"
                    except Exception as e:
                        logger.error(f"Failed to serialize top-tier result for {result.get('cv_id')}: {e}")
        except Exception as e:
            logger.error(f"Critical error in smart_screen_candidates_stream: {e}")
            yield json.dumps({"signal": "error", "detail": str(e)}) + "\n"
        finally:
            yield json.dumps({"signal": "complete", "processed": len(resumes)}) + "\n"
