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
            "max_output_tokens": 2048,
            "temperature": 0.1,
            "top_p": 0.9
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

    async def embed_documents(self, texts):
        if not self.client:
            raise RuntimeError("genai client was not set")
        if not self.embedding_model_id:
            raise RuntimeError("embedding model was not set")
        try:
            response = await self.client.aio.models.embed_content(
                model=self.embedding_model_id,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    title="Resume Snippet",
                    output_dimensionality=self.embedding_dimension
                )
            )

            embeddings = []
            for emb in response.embeddings:
                v = np.array(emb.values)
                norm = np.linalg.norm(v)
                if norm > 0:
                    v = v / norm
                embeddings.append(v.tolist())

            return embeddings
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

    async def extract_structured_resume(self, file_ref) -> LLMResponse:
        """Fallback: extract and structure a resume directly from an uploaded file."""
        try:
            prompt = RESUME_STRUCTURE_PROMPT + "\n\nExtract the resume from the uploaded document."

            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=[file_ref, prompt],
                config=types.GenerateContentConfig(**EXTRACTION_GENERATION_CONFIG)
            )

            result = json.loads(response.text)
            if isinstance(result, list):
                result = result[0]

            usage = self._parse_usage_metadata(response)
            return LLMResponse(content=result, usage_metadata=usage)
        except Exception as e:
            self.logger.error(f"Fallback extraction error: {e}")
            raise RuntimeError(f"Failed to extract resume via Gemini: {str(e)}")

    async def structure_resume_batch(self, markdown_texts: list[str]) -> LLMResponse:
        """Structure 2-3 locally-parsed markdown CVs into parsed_data JSON."""
        try:
            labeled_resumes = [
                f"=== RESUME {i+1} ===\n{text}\n=== END RESUME {i+1} ==="
                for i, text in enumerate(markdown_texts)
            ]
            combined = "\n\n".join(labeled_resumes)
            prompt = (
                RESUME_STRUCTURE_PROMPT
                + f"\n\nThere are {len(markdown_texts)} resumes below. "
                + f"Return a JSON array with {len(markdown_texts)} objects, one per resume, in the same order.\n\n"
                + combined
            )

            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(**BATCH_STRUCTURING_GENERATION_CONFIG)
            )

            result = json.loads(response.text)
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
