import re
import json
import asyncio
import logging
import time
from .BaseController import BaseController
from .ProjectController import ProjectController
from models.DB_schemas.chunk import Chunk
from models.DB_schemas.resume import Resume
from utils.constants import SECTION_KEYWORDS, MIME_MAP
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders import UnstructuredWordDocumentLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class ResumeProcessor(BaseController):
    def __init__(self):
        super().__init__()
        self.project_controller = ProjectController()

    # ── Document Loading ─────────────────────────────────────────────────

    def load_document(self, file_path: str, file_extension: str) -> str:
        if file_extension in ["pdf", "epub", "mobi"]:
            loader = PyMuPDF4LLMLoader(file_path)
        elif file_extension == "txt":
            loader = TextLoader(file_path, encoding="utf-8")
        elif file_extension in ["docx"]:
            loader = UnstructuredWordDocumentLoader(file_path, mode="single")
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")

        docs = loader.load()
        if not docs:
            return ""
        return "\n\n".join(doc.page_content for doc in docs)

    def validate_extraction(self, content: str) -> bool:
        if not content or len(content.strip()) < 100:
            return False

        content_lower = content.lower()
        matched = sum(1 for kw in SECTION_KEYWORDS if kw in content_lower)
        if matched < 2:
            return False

        garbled_count = len(re.findall(r'[^\x00-\x7F\u00C0-\u024F\u0600-\u06FF]', content))
        garbled_ratio = garbled_count / len(content) if content else 0
        if garbled_ratio > 0.3:
            return False

        return True

    # ── Content Extraction ───────────────────────────────────────────────

    async def extract_resume_content(
        self, generation_client, file_path: str, file_id: str, file_extension: str, usage_controller=None, project_id: str = None
    ) -> tuple[str, str]:
        try:
            content = self.load_document(file_path, file_extension)
            if self.validate_extraction(content):
                logger.info(f"Local parsing succeeded for {file_id}")
                return content, "local"
            else:
                logger.warning(f"Local parsing validation failed for {file_id}, using Gemini fallback")
        except Exception as e:
            logger.warning(f"Local parsing error for {file_id}: {e}, using Gemini fallback")

        return await self._extract_via_gemini(generation_client, file_path, file_id, file_extension, usage_controller, project_id)

    async def _extract_via_gemini(
        self, generation_client, file_path: str, file_id: str, file_extension: str, usage_controller, project_id
    ) -> tuple[str, str]:
        """Fallback extraction using Gemini file upload."""
        mime_type = MIME_MAP.get(file_extension, "application/octet-stream")
        file_ref = await generation_client.upload_file(file_path, mime_type)

        start_time = time.perf_counter()
        response = await generation_client.extract_structured_resume(file_ref)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        if usage_controller and project_id and response.usage_metadata:
            await usage_controller.log_usage(
                project_id=project_id,
                model_id=generation_client.model_id,
                action_type="cv_extraction_fallback",
                usage_metadata=response.usage_metadata,
                file_id=file_id,
                latency_ms=latency_ms
            )

        return json.dumps(response.content, ensure_ascii=False), "gemini_fallback"

    # ── Resume Building ──────────────────────────────────────────────────

    @staticmethod
    def _build_resume(project_id: str, file_id: str, parsed: dict, content: str, method: str) -> Resume:
        """Build a Resume object from parsed data."""
        return Resume(
            project_id=project_id,
            file_id=file_id,
            candidate_name=parsed.get("candidate_name", "Unknown"),
            contact_info=parsed.get("contact_info", {}),
            full_content=content,
            parsed_data=parsed.get("parsed_data", {}),
            extraction_method=method
        )

    # ── Structuring & Storing ────────────────────────────────────────────

    async def _store_fallback_items(self, fallback_items: list[dict], project_id: str, resume_model) -> list[Resume]:
        """Store pre-structured (Gemini fallback) items as Resume records."""
        stored = []
        for item in fallback_items:
            try:
                parsed = json.loads(item["content"])
                resume = self._build_resume(project_id, item["file_id"], parsed, item["content"], "gemini_fallback")
                created = await resume_model.create_resume(resume)
                stored.append(created)
            except Exception as e:
                logger.error(f"Error storing fallback resume {item['file_id']}: {e}")
        return stored

    async def _store_local_items(
        self, local_items: list[dict], project_id: str, generation_client, resume_model, usage_controller
    ) -> list[Resume]:
        """Structure locally-parsed items via LLM, then store as Resume records."""
        stored = []
        markdown_texts = [it["content"] for it in local_items]

        try:
            start_time = time.perf_counter()
            response = await generation_client.structure_resume_batch(markdown_texts)
            structured_results = response.content
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if usage_controller and response.usage_metadata:
                await usage_controller.log_usage(
                    project_id=project_id,
                    model_id=generation_client.model_id,
                    action_type="cv_structuring_batch",
                    usage_metadata=response.usage_metadata,
                    latency_ms=latency_ms
                )

            for i, item in enumerate(local_items):
                parsed = structured_results[i] if i < len(structured_results) else {
                    "candidate_name": "Unknown", "contact_info": {}, "parsed_data": {}
                }
                resume = self._build_resume(project_id, item["file_id"], parsed, item["content"], "local")
                created = await resume_model.create_resume(resume)
                stored.append(created)
        except Exception as e:
            logger.error(f"Batch structuring failed: {e}")
            for item in local_items:
                fallback_parsed = {"candidate_name": "Unknown", "contact_info": {}, "parsed_data": {}}
                resume = self._build_resume(project_id, item["file_id"], fallback_parsed, item["content"], "local")
                created = await resume_model.create_resume(resume)
                stored.append(created)

        return stored

    async def structure_and_store_batch(
        self,
        generation_client,
        items: list[dict],
        project_id: str,
        resume_model,
        usage_controller=None
    ) -> list[Resume]:
        local_items = [it for it in items if it["method"] == "local"]
        fallback_items = [it for it in items if it["method"] == "gemini_fallback"]

        fallback_resumes = await self._store_fallback_items(fallback_items, project_id, resume_model)
        local_resumes = await self._store_local_items(
            local_items, project_id, generation_client, resume_model, usage_controller
        ) if local_items else []

        return fallback_resumes + local_resumes

    # ── Chunking ─────────────────────────────────────────────────────────

    def chunk_from_parsed_data(self, parsed_data: dict, file_id: str, project_id: str) -> list[Chunk]:
        chunks = []
        order = 1

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
                        metadata={"file_id": file_id, "section_type": section_type},
                        chunk_order=order, project_id=project_id
                    ))
                    order += 1

        # List-of-dict sections
        for job in parsed_data.get("work_history", []):
            content = f"{job.get('title', '')} at {job.get('company', '')} ({job.get('dates', '')})\n{job.get('description', '')}"
            chunks.append(Chunk(
                content=content.strip(),
                metadata={"file_id": file_id, "section_type": "work_history"},
                chunk_order=order, project_id=project_id
            ))
            order += 1

        for edu in parsed_data.get("education", []):
            content = f"{edu.get('degree', '')} at {edu.get('institution', '')} ({edu.get('dates', '')})"
            chunks.append(Chunk(
                content=content.strip(),
                metadata={"file_id": file_id, "section_type": "education"},
                chunk_order=order, project_id=project_id
            ))
            order += 1

        for proj in parsed_data.get("projects", []):
            content = f"Project: {proj.get('name', '')}\n{proj.get('description', '')}"
            chunks.append(Chunk(
                content=content.strip(),
                metadata={"file_id": file_id, "section_type": "projects"},
                chunk_order=order, project_id=project_id
            ))
            order += 1

        return chunks

    def fallback_chunk(self, full_content: str, file_id: str, project_id: str) -> list[Chunk]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""],
            length_function=len
        )
        splits = splitter.split_text(full_content)
        return [
            Chunk(
                content=text,
                metadata={"file_id": file_id, "section_type": "raw"},
                chunk_order=i + 1, project_id=project_id
            )
            for i, text in enumerate(splits)
        ]

    # ── Main Pipeline ────────────────────────────────────────────────────

    async def process_and_store(
        self,
        generation_client,
        project_id: str,
        file_ids: list[str],
        resume_model,
        chunk_model,
        asset_model,
        vector_controller,
        project,
        do_reset: bool = False,
        extraction_client=None,
        usage_controller=None
    ):
        if do_reset:
            await resume_model.delete_resumes_by_project_id(project_id)
            await chunk_model.delete_chunks_by_project_id(project_id)

        assets = await asset_model.get_assets_by_project_id(project_id)
        if file_ids:
            assets = [a for a in assets if a.name in file_ids]
        if not assets:
            return {"processed": 0, "errors": []}

        processing_client = extraction_client if extraction_client else generation_client
        errors = []

        # Phase 1: Extract
        extracted_items = await self._extract_all(processing_client, assets, usage_controller, project_id, errors)

        # Phase 2: Structure & Store
        all_resumes = await self._structure_all(processing_client, extracted_items, project_id, resume_model, usage_controller, errors)

        # Phase 3: Chunk & Vectorize
        all_chunks = await self._chunk_and_vectorize(all_resumes, project_id, chunk_model, vector_controller, project, do_reset, errors)

        return {
            "processed": len(all_resumes),
            "chunks_created": len(all_chunks),
            "errors": errors
        }

    async def _extract_all(self, processing_client, assets, usage_controller, project_id, errors) -> list[dict]:
        """Extract content from all assets concurrently."""
        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)

        async def extract_one(asset):
            async with sem:
                try:
                    ext = asset.name.split(".")[-1].lower()
                    content, method = await self.extract_resume_content(
                        processing_client, asset.url, asset.name, ext, usage_controller, project_id
                    )
                    return {"file_id": asset.name, "content": content, "method": method}
                except Exception as e:
                    logger.error(f"Extraction failed for {asset.name}: {e}")
                    errors.append({"file_id": asset.name, "error": str(e)})
                    return None

        results = await asyncio.gather(*[extract_one(a) for a in assets])
        return [r for r in results if r is not None]

    async def _structure_all(self, processing_client, extracted_items, project_id, resume_model, usage_controller, errors) -> list[Resume]:
        """Structure and store extracted items in batches."""
        all_resumes = []
        batch_size = 3

        for i in range(0, len(extracted_items), batch_size):
            batch = extracted_items[i:i + batch_size]
            try:
                resumes = await self.structure_and_store_batch(
                    processing_client, batch, project_id, resume_model, usage_controller
                )
                all_resumes.extend(resumes)
            except Exception as e:
                logger.error(f"Batch processing error: {e}")
                for item in batch:
                    errors.append({"file_id": item["file_id"], "error": str(e)})

        return all_resumes

    async def _chunk_and_vectorize(self, all_resumes, project_id, chunk_model, vector_controller, project, do_reset, errors) -> list[Chunk]:
        """Chunk all resumes and upsert to vector DB."""
        all_chunks = []

        for resume in all_resumes:
            if resume.parsed_data:
                chunks = self.chunk_from_parsed_data(resume.parsed_data, resume.file_id, project_id)
            else:
                chunks = self.fallback_chunk(resume.full_content, resume.file_id, project_id)

            if chunks:
                await chunk_model.create_chunks_bulk(chunks)
                all_chunks.extend(chunks)

        if all_chunks:
            try:
                await vector_controller.upsert_vectors(project=project, chunks=all_chunks, do_reset=do_reset)
            except Exception as e:
                logger.error(f"Vector upsert error: {e}")
                errors.append({"file_id": "vector_upsert", "error": str(e)})

        return all_chunks
