import json
import logging
from typing import Optional, Dict, Any, List
import os
from groq import AsyncGroq
from ..LLMInterface import LLMInterface, LLMResponse
from utils.prompts import RESUME_STRUCTURE_PROMPT
from utils.file_loader import load_document
from utils.config import get_settings

logger = logging.getLogger(__name__)

class GroqProvider(LLMInterface):
    def __init__(self, api_key: str, model_id: str = None):
        self.api_key = api_key
        settings = get_settings()
        self._model_id = model_id or settings.DEFAULT_GROQ_MODEL
        
        if not self.api_key:
            raise ValueError("Groq API key is required")
            
        self.client = AsyncGroq(api_key=self.api_key)
        
        self.default_config = {
            "temperature": 0.1,
            "max_tokens": 2048,
            "top_p": 0.9,
        }

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def embedding_dimension(self) -> int:
        return 0

    @staticmethod
    def _parse_usage_metadata(response) -> dict:
        """Extract token usage from a Groq API response."""
        if not response.usage:
            return {}
        return {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }

    async def generate(self, prompt: str, config: Optional[Dict[str, Any]] = None) -> LLMResponse:
        try:
            # Filter and map config for Groq
            groq_config = self.default_config.copy()
            if config:
                groq_config.update(config)
            
            # Groq unsupported parameters or different names
            if "max_output_tokens" in groq_config:
                groq_config["max_tokens"] = groq_config.pop("max_output_tokens")
            
            # Remove Gemini-specific parameters
            groq_config.pop("response_mime_type", None)

            response = await self.client.chat.completions.create(
                model=self._model_id,
                messages=[{"role": "user", "content": prompt}],
                **groq_config
            )
            
            content = response.choices[0].message.content
            usage = self._parse_usage_metadata(response)
            return LLMResponse(content=content, usage_metadata=usage)
            
        except Exception as e:
            logger.error(f"Groq generation error: {e}")
            raise RuntimeError(f"Failed to generate content via Groq: {str(e)}")

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Groq doesn't have a standard embedding endpoint in the same way, 
        # or we might want to skip this for fallback consistency.
        # Returning empty or raising not implemented is safer than partial implementation.
        raise NotImplementedError("Embeddings are not supported by Groq fallback.")

    async def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError("Embeddings are not supported by Groq fallback.")

    async def upload_file(self, file_path: str, mime_type: str):
        """
        Groq doesn't have a File API for context like Gemini. 
        We return the local path as a reference.
        """
        if not os.path.exists(file_path):
             raise FileNotFoundError(f"File not found: {file_path}")
        return file_path

    async def extract_structured_resume(self, file_ref) -> LLMResponse:
        """
        Extract resume by loading text locally and sending to Groq JSON mode.
        file_ref is assumed to be the file_path returned by upload_file.
        """
        file_path = file_ref
        try:
            # 1. Load context locally
            ext = file_path.split('.')[-1].lower()
            content = load_document(file_path, ext)
            
            if not content:
                 raise ValueError(f"Could not extract text from {file_path}")

            # 2. Construct Prompt
            prompt = (
                f"{RESUME_STRUCTURE_PROMPT}\n\n"
                f"RESUME CONTENT:\n{content}"
            )

            # 3. Call Groq with JSON mode
            response = await self.client.chat.completions.create(
                model=self._model_id,
                messages=[
                    {"role": "system", "content": "You are a resume parser dealing with JSON output only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            result_text = response.choices[0].message.content
            result_json = json.loads(result_text)
            
            # Normalize list vs dict return if needed (Prompt asks for object, but sometimes...)
            if isinstance(result_json, list):
                 result_json = result_json[0]
                 
            usage = self._parse_usage_metadata(response)
            return LLMResponse(content=result_json, usage_metadata=usage)

        except Exception as e:
            logger.error(f"Groq extraction error: {e}")
            raise RuntimeError(f"Failed to extract resume via Groq: {str(e)}")

    async def structure_resume_batch(self, markdown_texts: List[str]) -> LLMResponse:
        """Structure a batch of text resumes."""
        try:
            labeled_resumes = [
                f"=== RESUME {i+1} ===\n{text}\n=== END RESUME {i+1} ==="
                for i, text in enumerate(markdown_texts)
            ]
            combined = "\n\n".join(labeled_resumes)
            
            prompt = (
                f"{RESUME_STRUCTURE_PROMPT}\n\n"
                f"There are {len(markdown_texts)} resumes below. "
                "Return a JSON object with a key 'resumes' containing an array of objects, one per resume.\n\n"
                f"{combined}"
            )

            response = await self.client.chat.completions.create(
                model=self._model_id,
                messages=[
                     {"role": "system", "content": "You are a bulk resume parser. Return JSON."},
                     {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            result_text = response.choices[0].message.content
            data = json.loads(result_text)
            
            # Handle potential wrapping formats "resumes": [...] or direct list
            result_list = data.get("resumes", data) if isinstance(data, dict) else data
            
            if not isinstance(result_list, list):
                 # Fallback normalization attempt
                 if isinstance(data, dict):
                     # Try to find any list value
                     for v in data.values():
                         if isinstance(v, list):
                             result_list = v
                             break
            
            if not isinstance(result_list, list):
                 result_list = [result_list] # Should probably warn

            usage = self._parse_usage_metadata(response)
            return LLMResponse(content=result_list, usage_metadata=usage)
            
        except Exception as e:
            logger.error(f"Groq batch structuring error: {e}")
            raise RuntimeError(f"Failed to structure resume batch via Groq: {str(e)}")
