import re
import json
import asyncio
import logging
from .BaseController import BaseController
from .ProjectController import ProjectController
from models.DB_schemas.chunk import Chunk
from models.DB_schemas.resume import Resume
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders import UnstructuredWordDocumentLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

SECTION_KEYWORDS = [
    "experience", "education", "skills", "summary",
    "objective", "work", "projects", "certifications",
    "qualifications", "employment", "profile", "contact"
]

MIME_MAP = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain"
}


class ResumeProcessor(BaseController):
    def __init__(self):
        super().__init__()
        self.project_controller = ProjectController()

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

    async def extract_resume_content(
        self, generation_client, file_path: str, file_id: str, file_extension: str
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

        mime_type = MIME_MAP.get(file_extension, "application/octet-stream")
        file_ref = await generation_client.upload_file(file_path, mime_type)
        result = await generation_client.extract_structured_resume(file_ref)
        return json.dumps(result, ensure_ascii=False), "gemini_fallback"

    async def structure_and_store_batch(
        self,
        generation_client,
        items: list[dict],
        project_id: str,
        resume_model
    ) -> list[Resume]:
        stored_resumes = []

        local_items = [it for it in items if it["method"] == "local"]
        fallback_items = [it for it in items if it["method"] == "gemini_fallback"]

        for item in fallback_items:
            try:
                parsed = json.loads(item["content"])
                resume = Resume(
                    project_id=project_id,
                    file_id=item["file_id"],
                    candidate_name=parsed.get("candidate_name", "Unknown"),
                    contact_info=parsed.get("contact_info", {}),
                    full_content=item["content"],
                    parsed_data=parsed.get("parsed_data", {}),
                    extraction_method="gemini_fallback"
                )
                created = await resume_model.create_resume(resume)
                stored_resumes.append(created)
            except Exception as e:
                logger.error(f"Error storing fallback resume {item['file_id']}: {e}")

        if local_items:
            markdown_texts = [it["content"] for it in local_items]
            try:
                structured_results = await generation_client.structure_resume_batch(markdown_texts)
                for i, item in enumerate(local_items):
                    parsed = structured_results[i] if i < len(structured_results) else {
                        "candidate_name": "Unknown", "contact_info": {}, "parsed_data": {}
                    }
                    resume = Resume(
                        project_id=project_id,
                        file_id=item["file_id"],
                        candidate_name=parsed.get("candidate_name", "Unknown"),
                        contact_info=parsed.get("contact_info", {}),
                        full_content=item["content"],
                        parsed_data=parsed.get("parsed_data", {}),
                        extraction_method="local"
                    )
                    created = await resume_model.create_resume(resume)
                    stored_resumes.append(created)
            except Exception as e:
                logger.error(f"Batch structuring failed: {e}")
                for item in local_items:
                    resume = Resume(
                        project_id=project_id,
                        file_id=item["file_id"],
                        candidate_name="Unknown",
                        contact_info={},
                        full_content=item["content"],
                        parsed_data={},
                        extraction_method="local"
                    )
                    created = await resume_model.create_resume(resume)
                    stored_resumes.append(created)

        return stored_resumes

    def chunk_from_parsed_data(self, parsed_data: dict, file_id: str, project_id: str) -> list[Chunk]:
        chunks = []
        order = 1

        if parsed_data.get("summary"):
            chunks.append(Chunk(
                content=parsed_data["summary"],
                metadata={"file_id": file_id, "section_type": "summary"},
                chunk_order=order, project_id=project_id
            ))
            order += 1

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

        skills = parsed_data.get("skills", [])
        if skills:
            chunks.append(Chunk(
                content="Skills: " + ", ".join(skills),
                metadata={"file_id": file_id, "section_type": "skills"},
                chunk_order=order, project_id=project_id
            ))
            order += 1

        certs = parsed_data.get("certifications", [])
        if certs:
            chunks.append(Chunk(
                content="Certifications: " + ", ".join(certs),
                metadata={"file_id": file_id, "section_type": "certifications"},
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

        languages = parsed_data.get("languages", [])
        if languages:
            chunks.append(Chunk(
                content="Languages: " + ", ".join(languages),
                metadata={"file_id": file_id, "section_type": "languages"},
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
        do_reset: bool = False
    ):
        if do_reset:
            await resume_model.delete_resumes_by_project_id(project_id)
            await chunk_model.delete_chunks_by_project_id(project_id)

        assets = await asset_model.get_assets_by_project_id(project_id)
        if file_ids:
            assets = [a for a in assets if a.name in file_ids]

        if not assets:
            return {"processed": 0, "errors": []}

        sem = asyncio.Semaphore(self.app_settings.LLM_CONCURRENCY_LIMIT)
        extracted_items = []
        errors = []

        async def extract_one(asset):
            async with sem:
                try:
                    ext = asset.name.split(".")[-1].lower()
                    content, method = await self.extract_resume_content(
                        generation_client, asset.url, asset.name, ext
                    )
                    return {"file_id": asset.name, "content": content, "method": method}
                except Exception as e:
                    logger.error(f"Extraction failed for {asset.name}: {e}")
                    errors.append({"file_id": asset.name, "error": str(e)})
                    return None

        results = await asyncio.gather(*[extract_one(a) for a in assets])
        extracted_items = [r for r in results if r is not None]

        all_resumes = []
        batch_size = 3
        for i in range(0, len(extracted_items), batch_size):
            batch = extracted_items[i:i + batch_size]
            try:
                resumes = await self.structure_and_store_batch(
                    generation_client, batch, project_id, resume_model
                )
                all_resumes.extend(resumes)
            except Exception as e:
                logger.error(f"Batch processing error: {e}")
                for item in batch:
                    errors.append({"file_id": item["file_id"], "error": str(e)})

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
                await vector_controller.upsert_vectors(
                    project=project, chunks=all_chunks, do_reset=do_reset
                )
            except Exception as e:
                logger.error(f"Vector upsert error: {e}")
                errors.append({"file_id": "vector_upsert", "error": str(e)})

        return {
            "processed": len(all_resumes),
            "chunks_created": len(all_chunks),
            "errors": errors
        }
