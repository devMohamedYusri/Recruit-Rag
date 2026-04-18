from .BaseDataModel import BaseDataModel
from .DB_schemas.asset import Asset
from pymongo import IndexModel
from bson import ObjectId

class AssetModel(BaseDataModel):
    """Model for managing uploaded file assets in MongoDB."""
    collection_setting_key: str = "ASSETS_COLLECTION"

    def __init__(self, db_client):
        super().__init__(db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        """Creates an instance and initializes the collection indexes."""
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        """Initializes MongoDB indexes for the assets collection."""
        indexes = Asset.get_indexes()
        models = [
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            ) for index in indexes
        ]

        if models:
            await self.collection.create_indexes(models)

    
    async def create_asset(self, asset_data: Asset):
        data = asset_data.model_dump(by_alias=True, exclude_none=True)
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return Asset(**data)

    async def get_asset_by_id(self, asset_id: str, user_id: object):
        record = await self.collection.find_one({
            "_id": ObjectId(asset_id) if ObjectId.is_valid(asset_id) else asset_id,
            "user_id": user_id
        })
        if record:
            return Asset(**record)
        return None
    
    async def get_assets_by_project_id(self, project_id: str, user_id: object):
        records = await self.collection.find({
            "project_id": project_id,
            "user_id": user_id
        }).to_list(length=None)
        return [Asset(**record) for record in records]
    
    async def delete_asset_by_id(self, asset_id: str, user_id: object):
        result = await self.collection.delete_one({
            "_id": ObjectId(asset_id) if ObjectId.is_valid(asset_id) else asset_id,
            "user_id": user_id
        })
        return result.deleted_count > 0

    async def delete_assets_by_project_id(self, project_id: str, user_id: object):
        result = await self.collection.delete_many({
            "project_id": project_id,
            "user_id": user_id
        })
        return result.deleted_count