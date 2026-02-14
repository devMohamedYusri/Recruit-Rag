from typing import Optional, Dict, Any
from google import genai
from google.genai import types
from ..LLMInterface import LLMInterface
import logging
import numpy as np

class GeminiProvider(LLMInterface):
    def __init__(self,
        api_key: str, 
        model_id: str = "gemini-2.0-flash",
        embedding_model_id: str = "gemini-embedding-001",
        embedding_dimension: int = 768
     ):
        self.api_key = api_key
        self.model_id = model_id 
        self.embedding_model_id=embedding_model_id
        self.embedding_dimension=embedding_dimension

        if not self.api_key:
            raise ValueError("Google API key is required")
            
        self.client = genai.Client(api_key=self.api_key)
        
        self.default_config = {
            "max_output_tokens": 2048, 
            "temperature": 0.1,
            "top_p": 0.9
        }
        self.logger=logging.getLogger(__name__)

    async def generate(self, prompt: str, config: Optional[Dict[str, Any]] = None) -> str:
        if not self.client:
           self.logger.error("genai client was not set")
           return None
        if not self.model_id:
           self.logger.error("generation model was not set")
           return None
        
        final_config_dict = self.default_config.copy()
        if config:
            if "max_tokens" in config:
                config["max_output_tokens"] = config.pop("max_tokens")
            final_config_dict.update(config)

        generation_config = types.GenerateContentConfig(**final_config_dict)

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=generation_config
            )
            
            return response.text
            
        except Exception as e:
            print(f"Gemini Error: {e}") 
            raise RuntimeError(f"Failed to generate content: {str(e)}")
        
    async def embed_documents(self, texts):
        if not self.client:
            self.logger.error("genai client was not set")
            return None
        if not self.embedding_model_id:
            self.logger.error("embedding model was not set")
            return None
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
            print(f"Embedding Doc Error: {e}")
            return []

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
            self.logger.error(f"Embedding Query Error: {e}")
            raise RuntimeError(f"Failed to embed query: {str(e)}")