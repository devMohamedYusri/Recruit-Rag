from .BaseDataModel import BaseDataModel
from .DB_schemas.screening_result import ScreeningResultDB
from pymongo import IndexModel
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ScreeningResultModel(BaseDataModel):
    collection_setting_key: str = "SCREENING_RESULTS_COLLECTION"

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = ScreeningResultDB.get_indexes()
        models = [
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            ) for index in indexes
        ]
        
        if models:
            try:
                await self.collection.create_indexes(models)
            except Exception as e:
                logger.warning(f"Failed to create indexes for ScreeningResultModel: {e}")

    @property
    def _write_sem(self):
        if not hasattr(self, "__write_sem"):
            import asyncio
            self.__write_sem = asyncio.Semaphore(20)
        return self.__write_sem

    async def create_screening_result(self, screening_data: ScreeningResultDB):
        data = screening_data.model_dump(by_alias=True, exclude_none=False)
        # Drop None _id to let MongoDB auto-generate it
        if data.get("_id") is None:
            del data["_id"]
            
        async with self._write_sem:
            result = await self.collection.insert_one(data)
            return result.inserted_id

    async def create_screening_results_bulk(self, results: list[ScreeningResultDB]):
        if not results:
            return []
            
        docs = []
        for r in results:
            d = r.model_dump(by_alias=True, exclude_none=False)
            if d.get("_id") is None:
                del d["_id"]
            docs.append(d)
            
        async with self._write_sem:
            result = await self.collection.insert_many(docs)
            return result.inserted_ids

    async def get_results_by_project(self, project_id: str, user_id: object, limit: int = 100) -> list[dict]:
        cursor = self.collection.find({"project_id": project_id, "user_id": user_id}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_latest_results_by_project(self, project_id: str, user_id: object) -> list[dict]:
        """
        Returns the latest screening result for each unique file_id in a project.
        """
        pipeline = [
            {"$match": {"project_id": project_id, "user_id": user_id}},
            {"$sort": {"timestamp": -1}},
            {
                "$group": {
                    "_id": "$file_id",
                    "doc": {"$first": "$$ROOT"}
                }
            },
            {"$replaceRoot": {"newRoot": "$doc"}},
            {"$sort": {"timestamp": -1}}
        ]
        cursor = await self.collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def get_latest_result_for_resume(self, project_id: str, file_id: str, user_id: object) -> Optional[dict]:
        return await self.collection.find_one(
            {"project_id": project_id, "file_id": file_id, "user_id": user_id},
            sort=[("timestamp", -1)]
        )

    async def delete_results_by_project(self, project_id: str, user_id: object):
        result = await self.collection.delete_many({"project_id": project_id, "user_id": user_id})
        return result.deleted_count
