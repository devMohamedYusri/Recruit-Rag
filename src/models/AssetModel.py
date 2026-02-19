from .BaseDataModel import BaseDataModel
from .DB_schemas.asset import Asset
from pymongo import IndexModel
from bson import ObjectId

class AssetModel(BaseDataModel):
    collection_setting_key:str="ASSETS_COLLECTION"
    def __init__(self, db_client):
        super().__init__(db_client)
        
    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance
    
    async def init_collection(self):
        indexes = Asset.get_indexes()
        models=[
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            )for index in indexes
        ]

        if models:
            await self.collection.create_indexes(models)
                
    async def create_asset(self, asset_data: Asset):
        data = asset_data.model_dump(by_alias=True, exclude_none=True)
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        
        return Asset(**data)
    async def get_asset_by_id(self,asset_id:str):
        record=await self.collection.find_one({
            "asset_id":asset_id
        })
        if record:
            return Asset(**record)
        return None
    
    async def get_assets_by_project_id(self,project_id:str):
        records = await self.collection.find({
            "project_id":ObjectId(project_id) if ObjectId.is_valid(project_id) else project_id
        }).to_list(length=None)
        return [Asset(**record) for record in records]
    
    async def delete_asset_by_id(self,asset_id:str):
        result=await self.collection.delete_one({
            "asset_id":asset_id
        })
        return result.deleted_count > 0
        