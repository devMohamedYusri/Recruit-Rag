import asyncio
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

    async def _embed_batch(self, batch_texts):
        import time
        t0 = time.perf_counter()
        dense_coro = self.embedding_model.embed_documents(batch_texts)
        dense_vectors = await dense_coro
        t_dense = time.perf_counter() - t0
        
        # Disabled Sparse Embeddings for timing test
        # t0 = time.perf_counter()
        # sparse_coro = asyncio.to_thread(lambda: list(self.sparse_embedding_model.embed(batch_texts)))
        # sparse_vectors = await sparse_coro
        # t_sparse = time.perf_counter() - t0
        t_sparse = 0
        sparse_vectors = [None] * len(batch_texts)
        
        return dense_vectors, sparse_vectors, t_dense, t_sparse

    async def upsert_vectors(self, project: Project, chunks: list[Chunk], do_reset: bool = False):
        collection_name = self.create_collection_name(project.project_id)
        
        if do_reset:
            await self.vector_client.delete_collection(collection_name)

        await self.vector_client.create_collection(
            collection_name=collection_name,
            embedding_dim=self.embedding_model.embedding_dimension,
        )

        import time
        # Extreme Parallel Embeddings
        BATCH_SIZE = 100
        batches = [chunks[i:i + BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]
        
        # 1. Start all embedding requests concurrently with a rate limit
        embed_sem = asyncio.Semaphore(10)
        
        async def _safe_embed(texts):
            async with embed_sem:
                return await self._embed_batch(texts)

        embed_tasks = []
        for batch in batches:
            texts = [chunk.content for chunk in batch]
            embed_tasks.append(_safe_embed(texts))
            
        batch_results = await asyncio.gather(*embed_tasks)
        
        total_dense_time = 0
        total_sparse_time = 0
        
        t_upsert_start = time.perf_counter()
        
        upsert_sem = asyncio.Semaphore(5)
        
        async def _safe_upsert(batch_idx, batch):
            async with upsert_sem:
                texts = [chunk.content for chunk in batch]
                metadata = [chunk.metadata for chunk in batch]
                dense_vectors, sparse_vectors, t_dense, t_sparse = batch_results[batch_idx]
                
                await self.vector_client.upsert_to_collection(
                    collection_name=collection_name,
                    vectors=dense_vectors,
                    metadata=metadata,
                    texts=texts,
                    sparse_vectors=sparse_vectors,
                )
                return t_dense, t_sparse

        upsert_tasks = [_safe_upsert(i, b) for i, b in enumerate(batches)]
        upsert_results = await asyncio.gather(*upsert_tasks)
        
        for t_dense, t_sparse in upsert_results:
            total_dense_time += t_dense
            total_sparse_time += t_sparse
        
        t_upsert = time.perf_counter() - t_upsert_start
        
        # Calculate unique extraction times by file_id
        unique_extraction_times = {}
        for chunk in chunks:
            file_id = chunk.metadata.get("file_id")
            ext_time = chunk.metadata.get("extraction_time", 0.0)
            if file_id and file_id not in unique_extraction_times:
                unique_extraction_times[file_id] = ext_time
                
        total_extraction_time = sum(unique_extraction_times.values())

        # Performance metrics logged for monitoring
        # Timing data: {len(unique_extraction_times)} files, {total_extraction_time:.2f}s extraction, {len(chunks)} chunks

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
        try:
            raw_results = await self.search_vectors(project, query_text, k=k)
        except (ValueError, Exception) as e:
            # Collection doesn't exist yet (resumes not processed)
            if "not found" in str(e).lower():
                return []
            raise
        
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