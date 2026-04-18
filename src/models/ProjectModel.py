from .BaseDataModel import BaseDataModel
from .DB_schemas.project import Project
from pymongo import IndexModel
from datetime import datetime

class ProjectModel(BaseDataModel):
    collection_setting_key: str = "PROJECTS_COLLECTION"
    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = Project.get_indexes()
        models = [
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            ) for index in indexes
        ]

        if models:
            await self.collection.create_indexes(models)

    async def create_project(self, project_data: Project):
        data = project_data.model_dump(by_alias=True)
        # Use project_id as the primary key if _id is not provided
        if "_id" not in data or data["_id"] is None:
            data["_id"] = project_data.project_id
            
        await self.collection.insert_one(data)
        return Project(**data)

    
    async def get_project_by_id(self, project_id: str, user_id: object):
        record = await self.collection.find_one({
            "project_id": project_id,
            "user_id": user_id
        })
        if record:
            return Project(**record)
        return None

    async def delete_project_by_id(self, project_id: str, user_id: object):
        result = await self.collection.delete_one({
            "project_id": project_id,
            "user_id": user_id
        })
        return result.deleted_count > 0

    async def get_all_projects(self, user_id: object, page: int = 1, page_size: int = 10):
        filter = {"user_id": user_id}
        total_docs = await self.count_documents(filter)
        total_pages = (total_docs + page_size - 1) // page_size
        skip = (page - 1) * page_size
        cursor = self.collection.find(filter).skip(skip).limit(page_size)
        projects = []
        async for document in cursor:
            projects.append(Project(**document))
        return projects, total_pages
