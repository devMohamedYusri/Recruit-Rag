from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class SearchResult(BaseModel):
    id: str
    score: float
    content: str
    metadata: Dict[str, Any]

class VectorDBInterface(ABC):
    @abstractmethod
    async def upsert(self, documents: List[Dict[str, Any]]):
        """
        Why: Handles text-to-vector conversion INSIDE the class.
        """
        pass
    
    @abstractmethod
    async def search_vector_only(self, query_vector: List[float], k: int = 5) -> List[SearchResult]:
        """
        Performs a pure semantic vector search.
        """
        pass
    
    @abstractmethod
    async def delete(self, doc_id: str):
        """
        Essential for when a candidate withdraws their application.
        """
        pass