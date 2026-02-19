from .BaseDataModel import BaseDataModel
from .DB_schemas.usage_log import UsageLog
from pymongo import IndexModel

class UsageLogModel(BaseDataModel):
    collection_setting_key: str = "USAGE_LOGS_COLLECTION"

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        # We can init collection indexes lazily or here. ResumeModel does it here.
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = UsageLog.get_indexes()
        models = []
        for index in indexes:
             # Handle direction if needed, simplified here
             keys = index['fields']
             models.append(IndexModel(
                keys,
                name=index['name'],
                unique=index.get('unique', False)
             ))
        
        if models:
            try:
                await self.collection.create_indexes(models)
            except Exception:
                pass # Indexes might exist

    async def log_usage(self, usage_data: UsageLog):
        data = usage_data.model_dump(by_alias=True, exclude_none=True)
        result = await self.collection.insert_one(data)
        return result.inserted_id

    async def get_total_tokens_by_project(self, project_id: str):
        pipeline = [
            {"$match": {"project_id": project_id}},
            {"$group": {
                "_id": "$project_id",
                "total_input": {"$sum": "$prompt_tokens"},
                "total_output": {"$sum": "$completion_tokens"},
                "total_all": {"$sum": "$total_tokens"},
                "count": {"$sum": 1}
            }}
        ]
        cursor = await self.collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        if result:
            return result[0]
        return {"total_input": 0, "total_output": 0, "total_all": 0, "count": 0}
