from .BaseDataModel import BaseDataModel
from .DB_schemas.resume import Resume
from pymongo import IndexModel
from bson import ObjectId


class ResumeModel(BaseDataModel):
    collection_setting_key: str = "RESUMES_COLLECTION"

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = Resume.get_indexes()
        models = [
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            ) for index in indexes
        ]
        if models:
            await self.collection.create_indexes(models)

    async def create_resume(self, resume_data: Resume):
        data = resume_data.model_dump(by_alias=True, exclude_none=True)
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return Resume(**data)

    async def get_resume_by_id(self, resume_id: str):
        record = await self.collection.find_one({
            "_id": ObjectId(resume_id) if ObjectId.is_valid(resume_id) else resume_id
        })
        if record:
            return Resume(**record)
        return None

    async def get_resumes_by_project_id(self, project_id: str):
        records = await self.collection.find({
            "project_id": project_id
        }).to_list(length=None)
        return [Resume(**record) for record in records]

    async def get_resumes_by_file_ids(self, project_id: str, file_ids: list[str]):
        records = await self.collection.find({
            "project_id": project_id,
            "file_id": {"$in": file_ids}
        }).to_list(length=None)
        return [Resume(**record) for record in records]

    async def delete_resumes_by_project_id(self, project_id: str):
        result = await self.collection.delete_many({
            "project_id": project_id
        })
        return result.deleted_count

    async def get_resumes_by_ids(self, resume_ids: list[str]):
        object_ids = [
            ObjectId(rid) if ObjectId.is_valid(rid) else rid
            for rid in resume_ids
        ]
        records = await self.collection.find({
            "_id": {"$in": object_ids}
        }).to_list(length=None)
        return [Resume(**record) for record in records]

