from abc import ABC, abstractmethod
from typing import List, Dict, Any
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


    @abstractmethod
    async def create_collection(self, collection_name: str, embedding_dim: int):
        """Create a named collection if it does not already exist."""
        pass

    @abstractmethod
    async def delete_collection(self, collection_name: str):
        """Delete an entire collection by name."""
        pass

    @abstractmethod
    async def get_collection_info(self, collection_name: str) -> dict:
        """Return metadata about a collection."""
        pass

    @abstractmethod
    async def upsert_to_collection(
        self,
        collection_name: str,
        vectors: List[List[float]],
        metadata: List[Dict[str, Any]],
        texts: List[str],
    ):
        """Upsert pre-embedded vectors into a specific collection."""
        pass

    @abstractmethod
    async def search_collection(
        self,
        collection_name: str,
        query_vector: List[float],
        k: int = 5,
    ) -> List[SearchResult]:
        """Search a specific collection by vector similarity."""
        pass

    @abstractmethod
    async def delete_points(self, collection_name: str, point_ids: List[str]):
        """Delete specific points from a collection."""
        pass