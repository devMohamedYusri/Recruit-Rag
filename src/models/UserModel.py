from .BaseDataModel import BaseDataModel
from .DB_schemas.user import User
from pymongo import IndexModel
from datetime import datetime, timezone
from bson import ObjectId


class UserModel(BaseDataModel):
    collection_setting_key: str = "USERS_COLLECTION"
    
    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = User.get_indexes()
        models = [
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            ) for index in indexes
        ]

        if models:
            await self.collection.create_indexes(models)

    async def create_user(self, user_data: User):
        data = user_data.model_dump(by_alias=True, exclude_none=True)
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return User(**data)

    async def get_user_by_email(self, email: str):
        record = await self.collection.find_one({"email": email})
        if record:
            return User(**record)
        return None

    async def get_user_by_id(self, user_id: object):
        # user._id is stored as ObjectId; cast string to ObjectId for correct lookup
        oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        record = await self.collection.find_one({"_id": oid})
        if record:
            return User(**record)
        return None


    async def update_user(self, user_id: object, update_data: dict):
        update_data["updated_at"] = datetime.now(timezone.utc)
        await self.collection.update_one({"_id": user_id}, {"$set": update_data})
        return await self.get_user_by_id(user_id)
