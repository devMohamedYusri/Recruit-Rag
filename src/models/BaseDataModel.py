from utils import get_settings

class BaseDataModel:
    def __init__(self, db_client, **kwargs):
        self.db_client = db_client
        self.settings = get_settings() 
        collection_name = getattr(self.settings, self.collection_setting_key)
        self.collection = self.db_client[collection_name]
        
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    async def count_documents(self, filter: dict = None):
        return await self.collection.count_documents(filter or {})