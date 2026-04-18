from .BaseDataModel import BaseDataModel
from .DB_schemas.job_description import JobDescription
from pymongo import IndexModel
from datetime import datetime, timezone


class JobDescriptionModel(BaseDataModel):
    collection_setting_key: str = "JOB_DESCRIPTIONS_COLLECTION"

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = JobDescription.get_indexes()
        models = [
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            ) for index in indexes
        ]
        if models:
            await self.collection.create_indexes(models)

    async def create_or_update_job_description(self, jd_data: JobDescription, user_id: object):
        data = jd_data.model_dump(by_alias=True, exclude_none=True)
        data["updated_at"] = datetime.now(timezone.utc)
        data["user_id"] = user_id

        existing = await self.collection.find_one({
            "project_id": jd_data.project_id,
            "user_id": user_id
        })
        if existing:
            await self.collection.update_one(
                {"project_id": jd_data.project_id, "user_id": user_id},
                {"$set": data}
            )
            updated = await self.collection.find_one({"project_id": jd_data.project_id, "user_id": user_id})
            return JobDescription(**updated)
        else:
            result = await self.collection.insert_one(data)
            data["_id"] = result.inserted_id
            return JobDescription(**data)

    async def get_by_project_id(self, project_id: str, user_id: object):
        record = await self.collection.find_one({
            "project_id": project_id,
            "user_id": user_id
        })
        if record:
            return JobDescription(**record)
        return None

    async def delete_by_project_id(self, project_id: str, user_id: object):
        result = await self.collection.delete_many({
            "project_id": project_id,
            "user_id": user_id
        })
        return result.deleted_count
