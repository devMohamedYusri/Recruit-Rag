from typing import Optional, Dict, Any
from google import genai
from google.genai import types
from ..LLMInterface import LLMInterface, LLMResponse
from utils.prompts import RESUME_STRUCTURE_PROMPT
from utils.constants import EXTRACTION_GENERATION_CONFIG, BATCH_STRUCTURING_GENERATION_CONFIG
import logging
import numpy as np
import json
import pathlib
import asyncio
from langsmith import traceable


class GeminiProvider(LLMInterface):
    def __init__(self,
        api_key: str,
        model_id: str = "gemini-1.5-flash",
        embedding_model_id: str = "gemini-embedding-001",
        embedding_dimension: int = 768
     ):
        self.api_key = api_key
        self._model_id = model_id
        self.embedding_model_id = embedding_model_id
        self._embedding_dimension = embedding_dimension

        if not self.api_key:
            raise ValueError("Google API key is required")

        self.client = genai.Client(api_key=self.api_key)

        self.default_config = {
            "max_output_tokens": 4096,
            "temperature": 0,
            "top_p": 0
        }
        self.logger = logging.getLogger(__name__)

    @property
    def embedding_dimension(self) -> int:
        return self._embedding_dimension

    @property
    def model_id(self) -> str:
        return self._model_id

    @staticmethod
    def _parse_usage_metadata(response) -> dict:
        """Extract token usage from a Gemini API response."""
        if not response.usage_metadata:
            return {}
        return {
            "prompt_tokens": response.usage_metadata.prompt_token_count,
            "completion_tokens": response.usage_metadata.candidates_token_count,
            "total_tokens": response.usage_metadata.total_token_count
        }

    @traceable(name="gemini_generate", run_type="llm")
    async def generate(self, prompt: str, config: Optional[Dict[str, Any]] = None) -> LLMResponse:
        if not self.client:
            raise RuntimeError("genai client was not set")
        if not self.model_id:
            raise RuntimeError("generation model was not set")

        final_config_dict = self.default_config.copy()
        if config:
            if "max_tokens" in config:
                config["max_output_tokens"] = config.pop("max_tokens")
            final_config_dict.update(config)

        generation_config = types.GenerateContentConfig(**final_config_dict)

        try:
            response = await self.client.aio.models.generate_content(
                model=self._model_id,
                contents=prompt,
                config=generation_config
            )
            usage = self._parse_usage_metadata(response)
            return LLMResponse(content=response.text, usage_metadata=usage)
        except Exception as e:
            self.logger.error(f"Gemini generation error: {e}")
            raise RuntimeError(f"Failed to generate content: {str(e)}")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.client:
            raise RuntimeError("genai client was not set")
        if not self.embedding_model_id:
            raise RuntimeError("embedding model was not set")
        
        # Gemini limit is 100 items per batch
        BATCH_SIZE = 100
        all_embeddings = []

        try:
            for i in range(0, len(texts), BATCH_SIZE):
                batch = texts[i : i + BATCH_SIZE]
                response = await self.client.aio.models.embed_content(
                    model=self.embedding_model_id,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        title="Resume Snippet",
                        output_dimensionality=self.embedding_dimension
                    )
                )

                for emb in response.embeddings:
                    v = np.array(emb.values)
                    norm = np.linalg.norm(v)
                    if norm > 0:
                        v = v / norm
                    all_embeddings.append(v.tolist())

            return all_embeddings
        except Exception as e:
            self.logger.error(f"Embedding doc error: {e}")
            raise RuntimeError(f"Failed to embed documents: {str(e)}")

    async def embed_query(self, text):
        try:
            response = await self.client.aio.models.embed_content(
                model=self.embedding_model_id,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=self.embedding_dimension
                )
            )

            v = np.array(response.embeddings[0].values)
            norm = np.linalg.norm(v)
            if norm > 0:
                v = v / norm

            return v.tolist()
        except Exception as e:
            self.logger.error(f"Embedding query error: {e}")
            raise RuntimeError(f"Failed to embed query: {str(e)}")

    async def upload_file(self, file_path: str, mime_type: str):
        """Upload a file to Gemini's File API (used for fallback extraction)."""
        try:
            file_ref = await asyncio.to_thread(
                self.client.files.upload,
                file=pathlib.Path(file_path),
                config={"mime_type": mime_type}
            )
            
            while file_ref.state and file_ref.state.name == "PROCESSING":
                await asyncio.sleep(1)
                file_ref = await asyncio.to_thread(
                    self.client.files.get,
                    name=file_ref.name
                )

            if file_ref.state and file_ref.state.name == "FAILED":
                raise RuntimeError(f"File processing failed for {file_path}")

            self.logger.info(f"File uploaded: {file_ref.name}")
            return file_ref
        except Exception as e:
            self.logger.error(f"File upload error: {e}")
            raise RuntimeError(f"Failed to upload file: {str(e)}")

    @traceable(name="gemini_extract_structured_resume", run_type="llm")
    async def extract_structured_resume(self, file_ref, prompt: str = None) -> LLMResponse:
        """Fallback: extract and structure a resume directly from an uploaded file."""
        from utils.prompts import RESUME_STRUCTURE_PROMPT
        from models.DB_schemas.screening import ExtractedResume

        final_prompt = prompt or RESUME_STRUCTURE_PROMPT
        schema = ExtractedResume.model_json_schema()
        schema_str = json.dumps(schema, indent=2)

        try:
            full_prompt = (
                f"{final_prompt}\n\n"
                f"You MUST return a JSON object that strictly adheres to the following JSON schema:\n{schema_str}\n\n"
                "Extract the resume from the uploaded document."
            )

            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=[file_ref, full_prompt],
                config=types.GenerateContentConfig(**EXTRACTION_GENERATION_CONFIG)
            )

            content_text = response.text
            if "```json" in content_text:
                content_text = content_text.split("```json")[-1].split("```")[0].strip()
            elif "```" in content_text:
                 content_text = content_text.split("```")[-1].split("```")[0].strip()

            result = json.loads(content_text, strict=False)
            if isinstance(result, list):
                result = result[0]

            usage = self._parse_usage_metadata(response)
            return LLMResponse(content=result, usage_metadata=usage)
        except Exception as e:
            self.logger.error(f"Fallback extraction error: {e}")
            raise RuntimeError(f"Failed to extract resume via Gemini: {str(e)}")

    @traceable(name="gemini_structure_resume_batch", run_type="llm")
    async def structure_resume_batch(self, markdown_texts: list[str], prompt: str = None) -> LLMResponse:
        """Structure 2-3 locally-parsed markdown CVs into parsed_data JSON."""
        from utils.prompts import RESUME_STRUCTURE_PROMPT
        from models.DB_schemas.screening import ExtractedResume

        final_prompt_base = prompt or RESUME_STRUCTURE_PROMPT

        try:
            labeled_resumes = [
                f"=== RESUME {i+1} ===\n{text}\n=== END RESUME {i+1} ==="
                for i, text in enumerate(markdown_texts)
            ]
            combined = "\n\n".join(labeled_resumes)
            
            schema = ExtractedResume.model_json_schema()
            schema_str = json.dumps(schema, indent=2)

            prompt_text = (
                f"{final_prompt_base}\n\n"
                f"There are {len(markdown_texts)} resumes below. "
                "Return a JSON object with a key 'resumes' containing an array of objects that strictly follow this JSON schema:\n"
                f"{schema_str}\n\n"
                f"{combined}"
            )

            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt_text,
                config=types.GenerateContentConfig(**BATCH_STRUCTURING_GENERATION_CONFIG)
            )

            content_text = response.text
            if "```json" in content_text:
                content_text = content_text.split("```json")[-1].split("```")[0].strip()
            elif "```" in content_text:
                 content_text = content_text.split("```")[-1].split("```")[0].strip()

            data = json.loads(content_text, strict=False)
            result = data.get("resumes", data) if isinstance(data, dict) else data

            if not isinstance(result, list):
                if isinstance(data, dict):
                     for v in data.values():
                         if isinstance(v, list):
                             result = v
                             break
            
            if not isinstance(result, list):
                 result = [result]

            if len(result) != len(markdown_texts):
                self.logger.warning(
                    f"Expected {len(markdown_texts)} structured resumes, got {len(result)}"
                )

            usage = self._parse_usage_metadata(response)
            return LLMResponse(content=result, usage_metadata=usage)
        except Exception as e:
            self.logger.error(f"Batch structuring error: {e}")
            raise RuntimeError(f"Failed to structure resume batch: {str(e)}")
