import uuid
from qdrant_client import AsyncQdrantClient, models
from typing import List, Dict, Any, Optional
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

    async def initialize(self):
        """
        Call this explicitly after creating the instance!
        Example: 
        db = QdrantdbProvider(config)
        await db.initialize()
        """
        if not await self.client.collection_exists(collection_name=self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedding_dim, 
                    distance=self.distance_metric
                )
            )

            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="text",
                field_schema=models.TextIndexParams(
                    type="text",
                    tokenizer=models.TokenizerType.WORD,
                    lowercase=True,
                    min_token_len=2
                )
            )
            print(f"Collection '{self.collection_name}' created with Full-Text Index.")

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
            wait=True
        )

    async def search_vector_only(self, query_vector: List[float], k: int = 5) -> List[SearchResult]:
        hits = await self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=k,
            with_payload=True
        )

        return [
            SearchResult(
                id=str(hit.id),
                score=hit.score,
                content=hit.payload.get("text", hit.payload.get("content", "")), 
                metadata={k: v for k, v in hit.payload.items() if k not in ["text", "content"]}
            ) for hit in hits
        ]

    async def delete(self, doc_id: str):
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[doc_id])
        )
