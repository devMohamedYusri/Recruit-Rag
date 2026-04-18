from utils import get_settings

class BaseDataModel:
    """Base class for all MongoDB data models."""
    def __init__(self, db_client, **kwargs):
        self.db_client = db_client
        self.settings = get_settings()
        collection_name = getattr(self.settings, self.collection_setting_key)
        self.collection = self.db_client[collection_name]

        for key, value in kwargs.items():
            setattr(self, key, value)

    async def count_documents(self, filter_query: dict = None):
        """Count documents in the collection matching the filter."""
        return await self.collection.count_documents(filter_query or {})
