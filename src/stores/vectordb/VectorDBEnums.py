from enum import Enum
from typing import Optional
from pydantic import BaseModel


class VectorDBEnum(Enum):
    QDRANT = "QDRANT"
    PGVECTOR = "PGVECTOR"


class DistanceMetric(Enum):
    COSINE = "cosine"
    DOT = "dot"
    EUCLIDEAN = "l2"
    MANHATTAN = "manhattan"


class VectorDBConfig(BaseModel):
    """
    Typed configuration for a vector database connection.

    Fields:
        path:            Local filesystem path for embedded Qdrant storage.
        api_key:         Authentication key — only needed when connecting to
                         a remote/cloud Qdrant instance (e.g. Qdrant Cloud).
                         Not required for local embedded mode.
        vector_db_type:  Which backend to use (matches VectorDBEnum values).
        collection_name: Name of the collection to store vectors in.
        embedding_dim:   Dimensionality of the embedding vectors.
        distance:        Distance metric for similarity search.
    """
    path: str
    api_key: Optional[str] = None
    vector_db_type: str
    collection_name: str
    embedding_dim: int
    distance: str = "cosine"
