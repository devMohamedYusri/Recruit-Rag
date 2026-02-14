from .BaseController import BaseController
from models import Chunk, Project


class VectorController(BaseController):
    def __init__(self, vector_client, embedding_model):
        super().__init__()
        self.vector_client = vector_client
        self.embedding_model = embedding_model

    def create_collection_name(self, project_id: str):
        return f"project_{project_id}".strip()

    async def reset_vector_db_collection(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.delete_collection(collection_name)

    async def upsert_vectors(self, project: Project, chunks: list[Chunk], do_reset: bool = False):
        collection_name = self.create_collection_name(project.project_id)
        text_chunks = [chunk.content for chunk in chunks]
        metadata = [chunk.metadata for chunk in chunks]
        vectors = await self.embedding_model.embed_documents(text_chunks)

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
        )
        return True

    async def search_vectors(self, project: Project, query_text: str, k: int = 5):
        collection_name = self.create_collection_name(project.project_id)
        query_vector = await self.embedding_model.embed_query(query_text)
        return await self.vector_client.search_collection(
            collection_name=collection_name,
            query_vector=query_vector,
            k=k,
        )

    async def vector_info(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.get_collection_info(collection_name)

    async def delete_vectors(self, project_id: str):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.delete_collection(collection_name)

    async def delete_vectors_by_ids(self, project_id: str, point_ids: list[str]):
        collection_name = self.create_collection_name(project_id)
        return await self.vector_client.delete_points(collection_name, point_ids)