from abc import ABC, abstractmethod
from typing import Dict,Optional,Any

class LLMInterface(ABC):
    @abstractmethod
    async def generate(self,prompt:str,config:Optional[Dict[str,Any]]=None):
        """
        Generates text.
        'config' can override model_id or temperature at runtime.
        """
        pass
    
    @abstractmethod
    async def embed_documents(self,texts:list[str]):
        """
        Embeds a list of texts for storage (Database).
        """
        pass
    
    @abstractmethod
    async def embed_query(self,text:str):
        """
        Embeds a single query for searching (Retrieval).
        """
        pass

    @abstractmethod
    async def upload_file(self, file_path: str, mime_type: str):
        """
        Upload a file to the LLM provider's File API.
        Returns a file reference for use in subsequent calls.
        """
        pass

    @abstractmethod
    async def extract_structured_resume(self, file_ref) -> dict:
        """
        Fallback: Extract and structure a resume from an uploaded file.
        Returns {candidate_name, contact_info, full_content, parsed_data}.
        """
        pass

    @abstractmethod
    async def structure_resume_batch(self, markdown_texts: list[str]) -> list[dict]:
        """
        Structure 2-3 locally-parsed markdown CVs into parsed_data JSON.
        Returns a list of {candidate_name, contact_info, parsed_data} dicts.
        """
        pass
