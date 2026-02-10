from abc import ABC, abstractmethod
from typing import Dict,Optional,Any

class LLMInterface(ABC):
    @abstractmethod
    def generate(self,prompt:str,config:Optional[Dict[str,Any]]=None):
        """
        Generates text.
        'config' can override model_id or temperature at runtime.
        """
        pass
    
    @abstractmethod
    def embed_documents(self,texts:list[str],document_type:str):
        """
        Embeds a list of texts for storage (Database).
        """
        pass
    
    @abstractmethod
    def embed_query(self,text:str):
        """
        Embeds a single query for searching (Retrieval).
        """
        pass