import logging
from typing import Optional, Dict, Any, List

from ..LLMInterface import LLMInterface, LLMResponse

logger = logging.getLogger(__name__)

class FallbackProvider(LLMInterface):
    """
    A composite provider that wraps a primary and a secondary provider.
    If the primary provider fails, it attempts to use the secondary provider.
    """
    def __init__(self, primary: LLMInterface, secondary: LLMInterface):
        self.primary = primary
        self.secondary = secondary

    @property
    def model_id(self) -> str:
        """Returns the model_id of the primary provider."""
        return self.primary.model_id

    @property
    def embedding_dimension(self) -> int:
        """Returns the embedding_dimension of the primary provider."""
        return self.primary.embedding_dimension

    async def generate(self, prompt: str, config: Optional[Dict[str, Any]] = None) -> LLMResponse:
        try:
            return await self.primary.generate(prompt, config)
        except Exception as e:
            logger.warning(f"Primary provider generation failed: {e}. Falling back to secondary.")
            return await self.secondary.generate(prompt, config)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Embeddings are typically model-specific and not easily interchangeable 
        # for vector search without re-indexing. Fallback is NOT supported for embeddings.
        return await self.primary.embed_documents(texts)

    async def embed_query(self, text: str) -> List[float]:
        # Same as embed_documents
        return await self.primary.embed_query(text)

    async def upload_file(self, file_path: str, mime_type: str):
        """
        Attempts to upload to primary. 
        Returns a dict reference containing both primary ref (if successful) and local path.
        """
        ref = {"path": file_path, "primary_ref": None}
        try:
            ref["primary_ref"] = await self.primary.upload_file(file_path, mime_type)
        except Exception as e:
            logger.warning(f"Primary provider file upload failed: {e}. Fallback operations will use local path.")
            # We don't raise here, we just don't have a primary ref. 
            # Operations requiring primary ref will fail or need fallback logic in extract.
        return ref

    async def extract_structured_resume(self, file_ref) -> LLMResponse:
        """
        file_ref is assumed to be the dict returned by upload_file above.
        """
        # 1. Try Primary if available
        if isinstance(file_ref, dict) and file_ref.get("primary_ref"):
            try:
                return await self.primary.extract_structured_resume(file_ref["primary_ref"])
            except Exception as e:
                logger.warning(f"Primary provider extraction failed: {e}. Falling back to secondary.")
        
        # 2. Try Secondary (using path)
        # Handle case where file_ref might be loose path or dict
        path = file_ref if isinstance(file_ref, str) else file_ref.get("path")
        
        if not path:
             raise ValueError("No valid file path available for fallback extraction.")
             
        return await self.secondary.extract_structured_resume(path)

    async def structure_resume_batch(self, markdown_texts: List[str]) -> LLMResponse:
        try:
            return await self.primary.structure_resume_batch(markdown_texts)
        except Exception as e:
            logger.warning(f"Primary provider batch structuring failed: {e}. Falling back to secondary.")
            return await self.secondary.structure_resume_batch(markdown_texts)
