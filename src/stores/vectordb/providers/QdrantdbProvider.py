import uuid
from qdrant_client import AsyncQdrantClient, models
from typing import List, Dict, Any
from ..VectorDBInterface import VectorDBInterface, SearchResult
from ..VectorDBEnums import DistanceMetric, VectorDBConfig


class QdrantdbProvider(VectorDBInterface):
    def __init__(self, config: VectorDBConfig):
        self.client = AsyncQdrantClient(path=config.path, api_key=config.api_key, timeout=60)
        self.collection_name = config.collection_name
        self.embedding_dim = config.embedding_dim

        distance_enum = DistanceMetric(config.distance)
        distance_map = {
            DistanceMetric.COSINE: models.Distance.COSINE,
            DistanceMetric.EUCLIDEAN: models.Distance.EUCLID,
            DistanceMetric.DOT: models.Distance.DOT,
            DistanceMetric.MANHATTAN: models.Distance.MANHATTAN,
        }
        self.distance_metric = distance_map.get(distance_enum, models.Distance.COSINE)

    # --- Per-project collection methods (core implementations) ---

    async def create_collection(self, collection_name: str, embedding_dim: int):
        if not await self.client.collection_exists(collection_name=collection_name):
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_dim,
                    distance=self.distance_metric,
                ),
                sparse_vectors_config={
                    "bm25": models.SparseVectorParams(
                        index=models.SparseIndexParams(
                            on_disk=False,
                        )
                    )
                },
            )
            await self.client.create_payload_index(
                collection_name=collection_name,
                field_name="text",
                field_schema=models.TextIndexParams(
                    type="text",
                    tokenizer=models.TokenizerType.WORD,
                    lowercase=True,
                    min_token_len=2,
                ),
            )

    async def delete_collection(self, collection_name: str):
        if await self.client.collection_exists(collection_name=collection_name):
            await self.client.delete_collection(collection_name=collection_name)

    async def get_collection_info(self, collection_name: str) -> dict:
        if not await self.client.collection_exists(collection_name=collection_name):
            return None
        info = await self.client.get_collection(collection_name=collection_name)
        return {
            "collection_name": collection_name,
            "status": info.status.value if info.status else None,
            "optimizer_status": str(info.optimizer_status) if info.optimizer_status else None,
            "points_count": info.points_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "segments_count": info.segments_count,
            "warnings": info.warnings,
            "config": info.config.model_dump() if info.config else None,
            "payload_schema": {k: v.model_dump() for k, v in info.payload_schema.items()} if info.payload_schema else None,
        }

    async def upsert_to_collection(
        self,
        collection_name: str,
        vectors: List[List[float]],
        metadata: List[Dict[str, Any]],
        texts: List[str],
        sparse_vectors: List[Any] = None,
    ):
        points = []
        if sparse_vectors is None:
            # If no sparse vectors provided, just use None for all
            sparse_iter = [None] * len(vectors)
        else:
            sparse_iter = sparse_vectors

        for i, (vector, meta, text, sparse_vec) in enumerate(zip(vectors, metadata, texts, sparse_iter)):
            point_id = str(uuid.uuid4())
            payload = meta.copy() if meta else {}
            payload["text"] = text
            
            # Construct vector argument: either list (dense only) or dict (dense + sparse)
            if sparse_vec:
                vector_data = {
                    "": vector, # Default unnamed dense vector
                    "bm25": models.SparseVector(
                        indices=sparse_vec.indices.tolist() if hasattr(sparse_vec, "indices") else sparse_vec["indices"],
                        values=sparse_vec.values.tolist() if hasattr(sparse_vec, "values") else sparse_vec["values"]
                    )
                }
            else:
                vector_data = vector

            points.append(
                models.PointStruct(id=point_id, vector=vector_data, payload=payload)
            )

        await self.client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

    async def search_collection(
        self,
        collection_name: str,
        query_vector: List[float],
        query_sparse_vector: Any = None,
        k: int = 10,
    ) -> List[SearchResult]:
        if query_sparse_vector:
            # Hybrid search with RRF fusion
            # Needs to convert SparseEmbedding to Qdrant SparseVector format if needed
            if hasattr(query_sparse_vector, "indices"):
                 indices = query_sparse_vector.indices.tolist()
                 values = query_sparse_vector.values.tolist()
            else:
                 indices = query_sparse_vector["indices"]
                 values = query_sparse_vector["values"]

            prefetch = [
                models.Prefetch(
                    query=query_vector,
                    using=None, # Default dense vector
                    limit=k,
                ),
                models.Prefetch(
                    query=models.SparseVector(indices=indices, values=values),
                    using="bm25",
                    limit=k,
                ),
            ]
            
            response = await self.client.query_points(
                collection_name=collection_name,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=k,
                with_payload=True,
            )
        else:
            # Dense-only search (fallback)
            response = await self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=k,
                with_payload=True,
            )
        return [
            SearchResult(
                id=str(point.id),
                score=point.score,
                content=point.payload.get("text", point.payload.get("content", "")),
                metadata={
                    k: v for k, v in point.payload.items() if k not in ["text", "content"]
                },
            )
            for point in response.points
        ]

    async def delete_points(self, collection_name: str, point_ids: List[str]):
        await self.client.delete(
            collection_name=collection_name,
            points_selector=models.PointIdsList(points=point_ids),
        )

    # --- Default collection methods (delegate to per-project methods) ---

    async def initialize(self):
        await self.create_collection(self.collection_name, self.embedding_dim)

    async def upsert(self, documents: List[Dict[str, Any]]):
        points = []
        for doc in documents:
            point_id = doc['id']
            try:
                if isinstance(point_id, str):
                    uuid.UUID(point_id)
            except ValueError:
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(point_id)))

            payload = doc.get('metadata', {}).copy()

            if 'text' in doc:
                payload['text'] = doc['text']
            elif 'content' in doc:
                payload['text'] = doc['content']

            points.append(models.PointStruct(
                id=point_id,
                vector=doc['vector'],
                payload=payload
            ))

        await self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    async def search_vector_only(self, query_vector: List[float], k: int = 5) -> List[SearchResult]:
        return await self.search_collection(self.collection_name, query_vector, k)

    async def delete(self, doc_id: str):
        await self.delete_points(self.collection_name, [doc_id])