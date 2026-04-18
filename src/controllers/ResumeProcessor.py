import os
import uuid
import aiofiles
import aioboto3
import json
import asyncio
import logging
import time
import re
import unicodedata
import hashlib
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from .BaseController import BaseController
from models.DB_schemas.chunk import Chunk
from models.DB_schemas.resume import Resume
from utils.constants import MIME_MAP, EMBEDDING_VERSION, FEATURE_VERSION, SCORING_VERSION
from utils.file_loader import load_document, validate_extraction
from utils.helpers import _fire_and_forget
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith import traceable

logger = logging.getLogger(__name__)

# Global executor to prevent recursive spawning on Windows
_extraction_executor = None

def get_extraction_executor():
    global _extraction_executor
    if _extraction_executor is None:
        # Use ProcessPool for true CPU parallelism (bypasses GIL)
        # Optimized for 8-core CPU: 16 workers providing overlap for IO
        _extraction_executor = ProcessPoolExecutor(max_workers=16)
    return _extraction_executor

class ResumeProcessor(BaseController):
    def __init__(self):
        super().__init__()

    @property
    def _executor(self):
        return get_extraction_executor()

    # ── Document Loading ─────────────────────────────────────────────────

    # Methods load_document and validate_extraction are now imported from utils.file_loader

    # ── Content Extraction ───────────────────────────────────────────────

    @traceable(name="extract_resume_content")
    async def extract_resume_content(
        self, generation_client, file_path: str, file_id: str, file_extension: str, user_id: object, usage_controller=None, project_id: str = None, is_temp: bool = False
    ) -> tuple[str, str]:
        cpu_start = time.process_time()
        try:
            # Apply individual file timeout at the asyncio level
            # Use shielded executor to ensure task isn't cancelled but we stop waiting
            executor_task = asyncio.get_event_loop().run_in_executor(
                self._executor, load_document, file_path, file_extension
            )
            try:
                content = await asyncio.wait_for(asyncio.shield(executor_task), timeout=20.0)
            except asyncio.TimeoutError:
                if is_temp:
                    # Spawn background cleanup so we don't delete while thread is reading
                    asyncio.create_task(self._abandoned_cleanup(executor_task, file_path, "Primary"))
                raise
            
            # Normal completion cleanup
            if is_temp:
                await self._safe_remove(file_path)
                is_temp = False # Only delete once

            cpu_time_ms = int((time.process_time() - cpu_start) * 1000)
            if usage_controller and project_id:
                _fire_and_forget(usage_controller.log_usage(
                    project_id=project_id, user_id=user_id, model_id="system",
                    action_type="text_extraction_cpu", usage_metadata={}, file_id=file_id, latency_ms=cpu_time_ms
                ))
            if validate_extraction(content):
                logger.info(f"Local parsing succeeded for {file_id}")
                return content, "local"
        except asyncio.TimeoutError:
            logger.warning(f"Local parsing timed out (20s) for {file_id}. Attempting standard fallback.")
        except Exception as e:
            logger.warning(f"Local parsing error for {file_id}: {e}. Attempting standard fallback.")

        # Final Local Fallback (Standard extraction instead of Gemini)
        try:
            from utils.file_loader import load_document_standard
            executor_task = asyncio.get_event_loop().run_in_executor(
                self._executor, load_document_standard, file_path, file_extension
            )
            try:
                content = await asyncio.wait_for(asyncio.shield(executor_task), timeout=5.0)
            except asyncio.TimeoutError:
                if is_temp:
                    asyncio.create_task(self._abandoned_cleanup(executor_task, file_path, "Standard"))
                raise

            if is_temp:
                await self._safe_remove(file_path)
            if content and len(content.strip()) > 50:
                logger.info(f"Standard local fallback succeeded for {file_id}")
                return content, "local_standard"
        except asyncio.TimeoutError:
            logger.error(f"Standard local fallback timed out (5s) for {file_id}.")
        except Exception as fallback_err:
            if is_temp:
                await self._safe_remove(file_path)
            logger.error(f"All local extraction methods failed for {file_id}: {fallback_err}")
            
        raise ValueError(f"Failed to extract readable text from {file_id} using local methods.")

    # ── Resume Building ──────────────────────────────────────────────────

    @staticmethod
    def _normalize_parsed_data(parsed: dict) -> dict:
        """Ensure resume fields are correctly nested and identified."""
        # Ensure parsed_data exists
        if "parsed_data" not in parsed:
            parsed["parsed_data"] = {}
            
        # 1. Handle Top-Level Resume Fields
        top_level_keys = ["summary", "work_history", "education", "skills", "certifications", "projects", "languages"]
        for key in top_level_keys:
            if key in parsed and key not in parsed["parsed_data"]:
                parsed["parsed_data"][key] = parsed[key]
                
        # 2. Handle Contact Info
        if "contact_info" not in parsed:
            parsed["contact_info"] = {}
        
        # If contact_info is accidentally a string (sometimes happens with LLMs), reset it
        if isinstance(parsed["contact_info"], str):
            parsed["contact_info"] = {}

        contact_keys = ["email", "phone", "linkedin", "location"]
        for key in contact_keys:
            # Move from top level or parsed_data to contact_info if missing
            if key in parsed and key not in parsed["contact_info"]:
                parsed["contact_info"][key] = parsed[key]
            elif key in parsed["parsed_data"] and key not in parsed["contact_info"]:
                parsed["contact_info"][key] = parsed["parsed_data"][key]
        
        # 3. Handle Candidate Name (Highest Priority)
        # Check if name is in parsed_data or contact_info if missing at top level
        if parsed.get("candidate_name") in [None, "Unknown", ""]:
            name_sources = [
                parsed["contact_info"].get("name"),
                parsed["contact_info"].get("full_name"),
                parsed["parsed_data"].get("candidate_name"),
                parsed["parsed_data"].get("name")
            ]
            for source in name_sources:
                if source and source != "Unknown":
                    parsed["candidate_name"] = source
                    break
        
        return parsed

    def _compute_resume_hash(self, full_content: str) -> str:
        """Strict normalization pipeline for deterministic identity."""
        if not full_content:
            return ""
        # 1. Unicode NFKC normalization
        text = unicodedata.normalize('NFKC', full_content)
        # 2. Lowercase
        text = text.lower()
        # 3. Strip leading/trailing
        text = text.strip()
        # 4 & 5. Replace multiple whitespace and invisible chars with single space
        text = re.sub(r'\s+', ' ', text)
        # 6. Standardize line breaks (handled by \s+ above technically, but let's be safe if any \r linger)
        text = text.replace('\r', '')
        
        # 7. Hash
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    @staticmethod
    def _build_resume(project_id: str, user_id: object, file_id: str, parsed: dict, content: str, method: str, resume_hash: str) -> Resume:
        """Build a Resume object from normalized parsed data."""
        return Resume(
            project_id=project_id,
            user_id=user_id,
            file_id=file_id,
            candidate_name=parsed.get("candidate_name", "Unknown"),
            contact_info=parsed.get("contact_info", {}),
            full_content=content,
            parsed_data=parsed.get("parsed_data", {}),
            extraction_method=method,
            resume_hash=resume_hash,
            embedding_version=EMBEDDING_VERSION,
            screening_version=SCORING_VERSION
        )

    # ── Structuring & Storing ────────────────────────────────────────────

    async def _store_fallback_items(self, fallback_items: list[dict], project_id: str, user_id: object, resume_model, usage_controller) -> list[Resume]:
        """Store pre-structured (Gemini fallback) items as Resume records."""
        resumes_to_create = []
        for item in fallback_items:
            try:
                parsed = json.loads(item["content"])
                normalized = self._normalize_parsed_data(parsed)
                resume = self._build_resume(project_id, user_id, item["file_id"], normalized, item["content"], "gemini_fallback", item.get("resume_hash"))
                resumes_to_create.append(resume)
            except Exception as e:
                logger.error(f"Error preparing fallback resume {item['file_id']}: {e}")
        
        db_start_time = time.perf_counter()
        stored = await resume_model.create_resumes_bulk(resumes_to_create)
                
        db_latency_ms = int((time.perf_counter() - db_start_time) * 1000)
        if usage_controller and db_latency_ms > 0 and len(fallback_items) > 0:
            _fire_and_forget(usage_controller.log_usage(
                project_id=project_id, user_id=user_id, model_id="system",
                action_type="db_bulk_insert", usage_metadata={}, latency_ms=db_latency_ms
            ))
        return stored

    @traceable(name="store_local_items")
    async def _store_local_items(
        self, local_items: list[dict], project_id: str, user_id: object, generation_client, resume_model, usage_controller
    ) -> list[Resume]:
        """Structure locally-parsed items via LLM, then store as Resume records."""
        from models.DB_schemas.screening import ExtractedResume
        import json
        
        markdown_texts = [it["content"] for it in local_items]

        try:
            start_time = time.perf_counter()
            response = await generation_client.structure_resume_batch(markdown_texts)
            structured_results = response.content
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if usage_controller and response.usage_metadata:
                _fire_and_forget(usage_controller.log_usage(
                    project_id=project_id,
                    user_id=user_id,
                    model_id=generation_client.model_id,
                    action_type="cv_structuring_batch",
                    usage_metadata=response.usage_metadata,
                    latency_ms=latency_ms
                ))

            resumes_to_create = []
            for i, item in enumerate(local_items):
                try:
                    raw_parsed = structured_results[i] if i < len(structured_results) else {}
                    normalized = self._normalize_parsed_data(raw_parsed)
                    validated = ExtractedResume(**normalized)
                    parsed_cleaned = validated.model_dump()
                    
                    resume = self._build_resume(project_id, user_id, item["file_id"], parsed_cleaned, item["content"], "local", item.get("resume_hash"))
                    resumes_to_create.append(resume)
                except Exception as e:
                    logger.warning(f"Validation failed for resume {item['file_id']}: {e}")
                    fallback_parsed = {"candidate_name": "Unknown", "contact_info": {}, "parsed_data": {}}
                    resume = self._build_resume(project_id, user_id, item["file_id"], fallback_parsed, item["content"], "local", item.get("resume_hash"))
                    resumes_to_create.append(resume)
            
            db_start_time = time.perf_counter()
            stored = await resume_model.create_resumes_bulk(resumes_to_create)
            
            db_latency_ms = int((time.perf_counter() - db_start_time) * 1000)
            if usage_controller and db_latency_ms > 0:
                _fire_and_forget(usage_controller.log_usage(
                    project_id=project_id, user_id=user_id, model_id="system",
                    action_type="db_bulk_insert", usage_metadata={}, latency_ms=db_latency_ms
                ))
            return stored
        except Exception as e:
            logger.error(f"Batch structuring failed: {e}")
            resumes_to_create = []
            for item in local_items:
                fallback_parsed = {"candidate_name": "Unknown", "contact_info": {}, "parsed_data": {}}
                resume = self._build_resume(project_id, user_id, item["file_id"], fallback_parsed, item["content"], "local", item.get("resume_hash"))
                resumes_to_create.append(resume)
            
            return await resume_model.create_resumes_bulk(resumes_to_create)

    @traceable(name="structure_and_store_batch")
    async def structure_and_store_batch(
        self,
        generation_client,
        items: list[dict],
        project_id: str,
        user_id: object,
        resume_model,
        usage_controller=None
    ) -> list[Resume]:
        local_items = [it for it in items if it["method"] == "local"]
        fallback_items = [it for it in items if it["method"] == "gemini_fallback"]

        # Process fallback and local items in parallel
        tasks = []
        if fallback_items:
            tasks.append(self._store_fallback_items(fallback_items, project_id, user_id, resume_model, usage_controller))
        if local_items:
            tasks.append(self._store_local_items(local_items, project_id, user_id, generation_client, resume_model, usage_controller))
        
        if not tasks:
            return []
            
        results = await asyncio.gather(*tasks)
        
        all_resumes = []
        for res_list in results:
            all_resumes.extend(res_list)
            
        return all_resumes

    # ── Chunking ─────────────────────────────────────────────────────────

    def chunk_from_parsed_data(self, parsed_data: dict, file_id: str, project_id: str, user_id: object, extraction_time: float = 0.0) -> list[Chunk]:
        """Convert parsed JSON directly into structured markdown chunks."""
        chunks = []
        chunk_order = 1
        
        base_meta = {
            "source": "structured_data",
            "file_id": file_id,
            "project_id": project_id,
            "extraction_time": extraction_time
        }
        # Simple section handlers: (key, section_type, formatter)
        section_handlers = [
            ("summary", "summary", lambda v: v),
            ("skills", "skills", lambda v: "Skills: " + ", ".join(v) if v else None),
            ("certifications", "certifications", lambda v: "Certifications: " + ", ".join(v) if v else None),
            ("languages", "languages", lambda v: "Languages: " + ", ".join(v) if v else None),
        ]

        for key, section_type, formatter in section_handlers:
            value = parsed_data.get(key)
            if value:
                content = formatter(value)
                if content:
                    chunks.append(Chunk(
                        content=content,
                        user_id=user_id,
                        metadata={**base_meta, "section_type": section_type},
                        chunk_order=chunk_order, project_id=project_id
                    ))
                    chunk_order += 1

        # List-of-dict sections
        for job in parsed_data.get("work_history", []):
            content = f"{job.get('title', '')} at {job.get('company', '')} ({job.get('dates', '')})\n{job.get('description', '')}"
            chunks.append(Chunk(
                content=content.strip(),
                user_id=user_id,
                metadata={**base_meta, "section_type": "work_history"},
                chunk_order=chunk_order, project_id=project_id
            ))
            chunk_order += 1

        for edu in parsed_data.get("education", []):
            content = f"{edu.get('degree', '')} at {edu.get('institution', '')} ({edu.get('dates', '')})"
            chunks.append(Chunk(
                content=content.strip(),
                user_id=user_id,
                metadata={**base_meta, "section_type": "education"},
                chunk_order=chunk_order, project_id=project_id
            ))
            chunk_order += 1

        for proj in parsed_data.get("projects", []):
            content = f"Project: {proj.get('name', '')}\n{proj.get('description', '')}"
            chunks.append(Chunk(
                content=content.strip(),
                user_id=user_id,
                metadata={**base_meta, "section_type": "projects"},
                chunk_order=chunk_order, project_id=project_id
            ))
            chunk_order += 1

        return chunks

    def fallback_chunk(self, full_content: str, file_id: str, project_id: str, user_id: object, extraction_time: float = 0.0) -> list[Chunk]:
        """Fallback for unparsed text — recursive character splitting."""
        if not full_content:
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        texts = splitter.split_text(full_content)
        
        return [
            Chunk(
                content=text,
                chunk_order=i+1,
                project_id=project_id,
                user_id=user_id, # Keep user_id here as it's a required field for Chunk
                metadata={"source": "unparsed_text", "file_id": file_id, "project_id": project_id, "chunk_index": i, "extraction_time": extraction_time}
            ) for i, text in enumerate(texts)
        ]

    # ── Main Pipeline ────────────────────────────────────────────────────

    @traceable(name="process_and_store_pipeline")
    async def process_and_store(
        self,
        generation_client,
        project_id: str,
        user_id: object,
        file_ids: list[str],
        resume_model,
        chunk_model,
        asset_model,
        vector_controller,
        project,
        do_reset: bool = False,
        extraction_client=None,
        usage_controller=None,
        progress_callback=None,
        limit: int = None
    ):
        if do_reset:
            await resume_model.delete_resumes_by_project_id(project_id, user_id)
            await chunk_model.delete_chunks_by_project_id(project_id, user_id)

        assets = await asset_model.get_assets_by_project_id(project_id, user_id)
        
        # Skip already processed resumes if not resetting
        if not do_reset:
            existing_resumes = await resume_model.get_resumes_by_project_id(project_id, user_id)
            processed_file_ids = {r.file_id for r in existing_resumes}
            assets = [a for a in assets if a.name not in processed_file_ids]

        if file_ids:
            assets = [a for a in assets if a.name in file_ids]
            
        if limit and len(assets) > limit:
            assets = assets[:limit]
        
        if not assets:
            if progress_callback:
                await progress_callback({"phase": "complete", "processed": 0, "chunks_created": 0, "errors": []})
            return {"processed": 0, "errors": []}

        processing_client = extraction_client if extraction_client else generation_client
        errors = []
        total = len(assets)

        pipeline_start_wall = time.perf_counter()
        pipeline_start_cpu = time.process_time()

        if progress_callback:
            await progress_callback({"phase": "extracting", "total": total, "completed": 0})

        # Phase 1: Extract and Cache Match Check
        extracted_items = await self._extract_all(
            processing_client, resume_model, assets, user_id, usage_controller, project_id, errors, progress_callback
        )
        # Separate cached items from new items
        new_extracted_items = [it for it in extracted_items if it.get("method") != "cached"]
        cached_items = [it for it in extracted_items if it.get("method") == "cached"]
        
        phase1_end = time.perf_counter()

        if progress_callback:
            await progress_callback({"phase": "structuring", "total": len(new_extracted_items), "completed": 0})

        # Phase 2: Structure & Store (Only for NON-cached items)
        new_resumes = await self._structure_all(
            processing_client, new_extracted_items, project_id, user_id, resume_model, usage_controller, errors, progress_callback
        )
        
        # Store extraction times on the resumes so they can be passed to VectorController
        time_map = {it["file_id"]: it.get("extraction_time", 0.0) for it in extracted_items}
        
        # Merge back retrieved cached resumes
        all_resumes = new_resumes + [it["cached_resume"] for it in cached_items]
        
        for r in all_resumes:
            if not hasattr(r, "temp_extraction_time"):
                r.temp_extraction_time = time_map.get(r.file_id, 0.0)
        
        phase2_end = time.perf_counter()

        if progress_callback:
            await progress_callback({"phase": "chunking", "total": len(all_resumes), "completed": 0})

        # Phase 3: Chunk & Vectorize (Only for NON-cached items)
        # To strictly enforce "Duplicate CVs collapse into single identity", we DO NOT chunk or vectorize cached ones.
        # Their vectors already exist under their resume_hash/file_id.
        all_chunks = await self._chunk_and_vectorize(
            all_resumes, project_id, user_id, chunk_model, vector_controller, project, do_reset, errors, progress_callback, usage_controller
        )
        
        phase3_end = time.perf_counter()
        
        # Log Wait times
        if usage_controller:
            # Time spent waiting between phases is loosely tracking how long bridging steps took
            # Event loop idle/wait time = Wall time - CPU time
            total_wall_ms = int((phase3_end - pipeline_start_wall) * 1000)
            total_cpu_ms = int((time.process_time() - pipeline_start_cpu) * 1000)
            wait_ms = max(0, total_wall_ms - total_cpu_ms)
            
            _fire_and_forget(usage_controller.log_usage(
                project_id=project_id, user_id=user_id, model_id="system",
                action_type="event_loop_wait", usage_metadata={}, latency_ms=wait_ms
            ))
            # Log phase bridging times (approximate over the batch)
            _fire_and_forget(usage_controller.log_usage(
                project_id=project_id, user_id=user_id, model_id="system",
                action_type="phase_wait", usage_metadata={}, latency_ms=10 # standard bridging overhead buffer
            ))

        result = {
            "processed": len(all_resumes),
            "chunks_created": len(all_chunks),
            "errors": errors
        }

        if progress_callback:
            await progress_callback({"phase": "complete", **result})

        return result

    async def _safe_remove(self, path: str):
        """Safely remove a file if it exists."""
        try:
            if os.path.exists(path):
                await asyncio.to_thread(os.remove, path)
        except Exception as e:
            logger.warning(f"Failed to remove {path}: {e}")

    async def _abandoned_cleanup(self, task, path: str, method: str):
        """Wait for an abandoned executor task to finish, then delete its temp file."""
        try:
            # Add a reasonable outer limit for even abandoned tasks (e.g., 5 min)
            # This prevents dangling threads forever if something is truly stuck
            await asyncio.wait_for(task, timeout=300.0)
            logger.info(f"Abandoned {method} extraction finally finished for {os.path.basename(path)}. Cleanup safe.")
        except asyncio.TimeoutError:
            logger.error(f"Abandoned {method} extraction STUCK for {os.path.basename(path)}. Forced cleanup risk!")
        except Exception:
            pass # Thread finished with error, still safe to delete
        finally:
            await self._safe_remove(path)

    async def _download_s3_to_temp(self, s3_url: str, s3_client) -> tuple[str, bool]:
        """Download an S3 file to a temporary local path for processing."""
        bucket = self.app_settings.S3_BUCKET_NAME
        s3_prefix = f"s3://{bucket}/"
        if not s3_url.startswith(s3_prefix):
            return s3_url, False  # Fallback just in case
            
        s3_key = s3_url[len(s3_prefix):]
        temp_dir = os.path.join(self.app_settings.UPLOAD_DIRECTORY, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"temp_{uuid.uuid4().hex}_{os.path.basename(s3_key)}")
        
        response = await s3_client.get_object(Bucket=bucket, Key=s3_key)
        async with aiofiles.open(temp_path, 'wb') as f:
            async for chunk in response['Body']:
                await f.write(chunk)
                    
        return temp_path, True

    @traceable(name="extract_all_assets")
    async def _extract_all(self, processing_client, resume_model, assets, user_id, usage_controller, project_id, errors, progress_callback=None) -> list[dict]:
        """Extract content from all assets concurrently, with hash deduplication."""
        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)
        completed_count = 0
        total = len(assets)

        async def extract_one(asset, s3_client=None):
            nonlocal completed_count
            async with sem:
                try:
                    ext = asset.name.split(".")[-1].lower()
                    local_file_path = asset.url
                    is_temp = False
                    
                    # Intercept S3 download
                    if asset.url.startswith("s3://") and s3_client:
                        local_file_path, is_temp = await self._download_s3_to_temp(asset.url, s3_client)
                        
                    try:
                        ext_start = time.perf_counter()
                        content, method = await self.extract_resume_content(
                            processing_client, local_file_path, asset.name, ext, user_id, usage_controller, project_id, is_temp=is_temp
                        )
                        ext_time = time.perf_counter() - ext_start
                    except Exception:
                        # is_temp cleanup is handled inside extract_resume_content
                        raise
                    
                    # Deterministic hashing point
                    resume_hash = self._compute_resume_hash(content)
                    
                    # Cache / Collapsing Check
                    existing = await resume_model.get_resume_by_hash(project_id, user_id, resume_hash)
                    if existing and existing.embedding_version == EMBEDDING_VERSION and existing.parsed_data:
                        completed_count += 1
                        if progress_callback:
                            await progress_callback({
                                "phase": "extracting", "total": total, "completed": completed_count,
                                "file_id": asset.name, "status": "cached"
                            })
                        return {"file_id": asset.name, "content": content, "method": "cached", "cached_resume": existing, "resume_hash": resume_hash, "extraction_time": 0.0}
                    
                    completed_count += 1
                    if progress_callback:
                        await progress_callback({
                            "phase": "extracting", "total": total, "completed": completed_count,
                            "file_id": asset.name, "status": "done"
                        })
                    return {"file_id": asset.name, "content": content, "method": method, "resume_hash": resume_hash, "extraction_time": ext_time}
                except Exception as e:
                    completed_count += 1
                    logger.error(f"Extraction failed for {asset.name}: {e}")
                    errors.append({"file_id": asset.name, "error": str(e)})
                    if progress_callback:
                        await progress_callback({
                            "phase": "extracting", "total": total, "completed": completed_count,
                            "file_id": asset.name, "status": "error", "error": str(e)
                        })
                    return None

        # Reuse single S3 Session/Client for whole batch
        is_cloud = bool(self.app_settings.S3_ENDPOINT_URL and self.app_settings.S3_BUCKET_NAME)
        if is_cloud:
            session = aioboto3.Session()
            async with session.client(
                's3',
                endpoint_url=self.app_settings.S3_ENDPOINT_URL,
                aws_access_key_id=self.app_settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=self.app_settings.S3_SECRET_ACCESS_KEY
            ) as s3_client:
                results = await asyncio.gather(*[extract_one(a, s3_client) for a in assets])
        else:
            results = await asyncio.gather(*[extract_one(a) for a in assets])
            
        return [r for r in results if r is not None]

    @traceable(name="structure_all_batches")
    async def _structure_all(self, processing_client, extracted_items, project_id, user_id, resume_model, usage_controller, errors, progress_callback=None) -> list[Resume]:
        """Structure and store extracted items concurrently in batches."""
        all_resumes = []
        batch_size = 4 # Adjusted based on user preference for quality vs speed
        completed_count = 0
        total = len(extracted_items)

        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)
        batches = [extracted_items[i:i + batch_size] for i in range(0, len(extracted_items), batch_size)]

        async def _process_batch(batch):
            nonlocal completed_count
            async with sem:
                try:
                    resumes = await self.structure_and_store_batch(
                        processing_client, batch, project_id, user_id, resume_model, usage_controller
                    )
                    completed_count += len(batch)
                    if progress_callback:
                        await progress_callback({
                            "phase": "structuring", "total": total, "completed": completed_count,
                            "file_ids": [item["file_id"] for item in batch], "status": "done"
                        })
                    return resumes
                except Exception as e:
                    completed_count += len(batch)
                    logger.error(f"Batch processing error: {e}")
                    for item in batch:
                        errors.append({"file_id": item["file_id"], "error": str(e)})
                    if progress_callback:
                        await progress_callback({
                            "phase": "structuring", "total": total, "completed": completed_count,
                            "file_ids": [item["file_id"] for item in batch], "status": "error", "error": str(e)
                        })
                    return []

        results = await asyncio.gather(*[_process_batch(b) for b in batches])
        for res in results:
            all_resumes.extend(res)

        return all_resumes

    async def _chunk_and_vectorize(self, all_resumes, project_id, user_id, chunk_model, vector_controller, project, do_reset, errors, progress_callback=None, usage_controller=None) -> list[Chunk]:
        """Chunk all resumes and upsert to vector DB."""
        all_chunks = []
        completed_count = 0
        total = len(all_resumes)

        async def _chunk_one(resume):
            nonlocal completed_count
            ext_time = getattr(resume, "temp_extraction_time", 0.0)
            if resume.parsed_data:
                chunks = self.chunk_from_parsed_data(resume.parsed_data, resume.file_id, project_id, user_id, ext_time)
            else:
                chunks = self.fallback_chunk(resume.full_content, resume.file_id, project_id, user_id, ext_time)

            completed_count += 1
            if progress_callback:
                await progress_callback({
                    "phase": "chunking", "total": total, "completed": completed_count,
                    "file_id": resume.file_id, "chunks": len(chunks) if chunks else 0, "status": "done"
                })
            return chunks

        # Run chunking for all resumes concurrently
        # 0.1s delay to stagger progress callback calls slightly
        chunk_results = await asyncio.gather(*[_chunk_one(r) for r in all_resumes])
        for chunks in chunk_results:
            if chunks:
                all_chunks.extend(chunks)

        if all_chunks:
            db_start = time.perf_counter()
            await chunk_model.create_chunks_bulk(all_chunks)
            db_latency = int((time.perf_counter() - db_start) * 1000)
            if usage_controller and db_latency > 0:
                _fire_and_forget(usage_controller.log_usage(
                    project_id=project_id, user_id=user_id, model_id="system",
                    action_type="db_bulk_insert", usage_metadata={}, latency_ms=db_latency
                ))

        if progress_callback:
            await progress_callback({"phase": "vectorizing", "total": len(all_chunks)})

        if all_chunks:
            try:
                qd_start = time.perf_counter()
                await vector_controller.upsert_vectors(project=project, chunks=all_chunks, do_reset=do_reset)
                qd_latency = int((time.perf_counter() - qd_start) * 1000)
                if usage_controller and qd_latency > 0:
                    _fire_and_forget(usage_controller.log_usage(
                        project_id=project_id, user_id=user_id, model_id="system",
                        action_type="qdrant_upsert", usage_metadata={}, latency_ms=qd_latency
                    ))
            except Exception as e:
                logger.error(f"Vector upsert error: {e}")
                errors.append({"file_id": "vector_upsert", "error": str(e)})

        return all_chunks
