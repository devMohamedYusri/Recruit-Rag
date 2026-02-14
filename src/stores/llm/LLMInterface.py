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