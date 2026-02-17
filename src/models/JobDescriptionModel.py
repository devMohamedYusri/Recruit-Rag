from .BaseDataModel import BaseDataModel
from .DB_schemas.job_description import JobDescription
from pymongo import IndexModel
from datetime import datetime


class JobDescriptionModel(BaseDataModel):
    collection_setting_key: str = "JOB_DESCRIPTIONS_COLLECTION"

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.collection = self.db_client[self.collection_setting_key]

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

    async def create_or_update_job_description(self, jd_data: JobDescription):
        data = jd_data.model_dump(by_alias=True, exclude_none=True)
        data["updated_at"] = datetime.now().isoformat()

        existing = await self.collection.find_one({"project_id": jd_data.project_id})
        if existing:
            await self.collection.update_one(
                {"project_id": jd_data.project_id},
                {"$set": data}
            )
            updated = await self.collection.find_one({"project_id": jd_data.project_id})
            return JobDescription(**updated)
        else:
            result = await self.collection.insert_one(data)
            data["_id"] = result.inserted_id
            return JobDescription(**data)

    async def get_by_project_id(self, project_id: str):
        record = await self.collection.find_one({"project_id": project_id})
        if record:
            return JobDescription(**record)
        return None
