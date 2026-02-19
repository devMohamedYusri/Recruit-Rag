from .BaseDataModel import BaseDataModel
from .DB_schemas.project import Project
from pymongo import IndexModel

class ProjectModel(BaseDataModel):
    collection_setting_key:str="PROJECTS_COLLECTION"
    def __init__(self,db_client:object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = Project.get_indexes()
        models=[
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            )for index in indexes
        ]

        if models:
            await self.collection.create_indexes(models)

    async def create_project(self,project_data:Project):
        data = project_data.model_dump(by_alias=True, exclude_none=True)
        result=await self.collection.insert_one(data)
        return str(result.inserted_id)
    
    async def get_project_or_create_one(self, project_id: str):
        record = await self.collection.find_one({"project_id": project_id})
        if not record:
            default_project = Project(project_id=project_id)
            await self.create_project(default_project)
            return default_project
        return Project(**record)
    
    async def get_project_by_id(self,project_id:str):
        record=await self.collection.find_one({
            "project_id":project_id
        })
        if record:
            return Project(**record)
        return None
    async def delete_project_by_id(self,project_id:str):
        result=await self.collection.delete_one({
            "project_id":project_id
        })
        return result.deleted_count > 0
    async def get_all_projects(self, page: int = 1, page_size: int = 10):
        total_docs = await self.count_documents()
        total_pages = (total_docs + page_size - 1) // page_size
        skip = (page - 1) * page_size
        cursor = self.collection.find().skip(skip).limit(page_size)
        projects = []
        async for document in cursor:
            projects.append(Project(**document))
        return projects, total_pages
