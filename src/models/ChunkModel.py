from .DB_schemas.chunk import Chunk
from .BaseDataModel import BaseDataModel
from bson import ObjectId
from pymongo import IndexModel, InsertOne


class ChunkModel(BaseDataModel):
    collection_setting_key:str="CHUNKS_COLLECTION"
    def __init__(self,db_client:object):
        super().__init__(db_client=db_client)
        self.collection = self.db_client[self.collection_setting_key]

    @classmethod
    async def create_instance(cls,db_client:object):
        instance=cls(db_client=db_client)
        await instance.init_collection()
        return instance


    async def init_collection(self):
        indexes = Chunk.get_indexes()
        models=[
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            )for index in indexes
        ]

        if models:
            await self.collection.create_indexes(models)

    async def create_chunk(self,chunk_data:Chunk):
        data=chunk_data.model_dump(by_alias=True,exclude_none=True)
        result=await self.collection.insert_one(data)
        return str(result.inserted_id)
    
    async def get_chunk(self,chunk_id:str):
        result=await self.collection.find_one(
            {
               "_id":ObjectId(chunk_id)
            }
        )
        if result is None:
            return None
        return Chunk(**result)
        
    async def create_chunks_bulk(self,chunks:list[Chunk],batch_size:int=200):
        for i in range(0,len(chunks),batch_size):
            batch=chunks[i:i+batch_size]
            data_batch=[chunk.model_dump(by_alias=True,exclude_none=True) for chunk in batch]
            Operations=[InsertOne(data) for data in data_batch]
            await self.collection.bulk_write(Operations)
        return len(chunks)
    async def delete_chunks_by_project_id(self,project_id:str):
        result=await self.collection.delete_many({
            "project_id":ObjectId(project_id) if ObjectId.is_valid(project_id) else project_id
        })
        return result.deleted_count
        