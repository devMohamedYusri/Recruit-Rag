from .BaseController import BaseController
from models import Chunk, Project
from fastembed import SparseTextEmbedding


class VectorController(BaseController):
    def __init__(self, vector_client, embedding_model):
        super().__init__()
        self.vector_client = vector_client
        self.embedding_model = embedding_model
        # Initialize sparse embedding model (BM25)
        self.sparse_embedding_model = SparseTextEmbedding(model_name="Qdrant/bm25")

    def create_collection_name(self, project_id: str):
        return f"project_{project_id}".strip()

    async def reset_vector_db_collection(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.delete_collection(collection_name)

    async def upsert_vectors(self, project: Project, chunks: list[Chunk], do_reset: bool = False):
        collection_name = self.create_collection_name(project.project_id)
        text_chunks = [chunk.content for chunk in chunks]
        metadata = [chunk.metadata for chunk in chunks]
        
        # Generate dense embeddings
        vectors = await self.embedding_model.embed_documents(text_chunks)
        
        # Generate sparse embeddings (generator, so convert to list)
        sparse_vectors = list(self.sparse_embedding_model.embed(text_chunks))

        if do_reset:
            await self.vector_client.delete_collection(collection_name)

        await self.vector_client.create_collection(
            collection_name=collection_name,
            embedding_dim=self.embedding_model.embedding_dimension,
        )
        await self.vector_client.upsert_to_collection(
            collection_name=collection_name,
            vectors=vectors,
            metadata=metadata,
            texts=text_chunks,
            sparse_vectors=sparse_vectors,
        )
        return True

    async def search_vectors(self, project: Project, query_text: str, k: int = 5):
        collection_name = self.create_collection_name(project.project_id)
        
        # Generate dense query vector
        query_vector = await self.embedding_model.embed_query(query_text)
        
        # Generate sparse query vector (returns generator, get first item)
        query_sparse_vector = list(self.sparse_embedding_model.embed([query_text]))[0]

        return await self.vector_client.search_collection(
            collection_name=collection_name,
            query_vector=query_vector,
            query_sparse_vector=query_sparse_vector,
            k=k,
        )

    async def search_and_aggregate(self, project: Project, query_text: str, k: int = 1000) -> list[dict]:
        """
        Performs hybrid search and aggregates chunk scores to resume-level scores.
        Strategy: Sum of top 3 chunk scores per file.
        """
        raw_results = await self.search_vectors(project, query_text, k=k)
        
        file_scores = {}
        file_content_map = {} # Store best chunk content for preview

        for res in raw_results:
            file_id = res.metadata.get("file_id")
            if not file_id:
                continue
            
            if file_id not in file_scores:
                file_scores[file_id] = []
                file_content_map[file_id] = res.content
            
            file_scores[file_id].append(res.score)

        aggregated = []
        for file_id, scores in file_scores.items():
            # Strategy: Average of top 3 chunks (or fewer if less than 3)
            # This captures "peak relevance" better than simple average
            top_scores = sorted(scores, reverse=True)[:3]
            avg_score = sum(top_scores) / len(top_scores)
            
            aggregated.append({
                "file_id": file_id,
                "score": avg_score,
                "preview": file_content_map[file_id]
            })

        # Sort by final score desc
        aggregated.sort(key=lambda x: x["score"], reverse=True)
        return aggregated

    async def vector_info(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.get_collection_info(collection_name)

    async def delete_vectors(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.delete_collection(collection_name)

    async def delete_vectors_by_ids(self, project_id: str, point_ids: list[str]):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.delete_points(collection_name, point_ids)