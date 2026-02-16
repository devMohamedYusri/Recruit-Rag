from .VectorDBEnums import VectorDBEnum, VectorDBConfig
from .VectorDBInterface import VectorDBInterface
from .providers.QdrantdbProvider import QdrantdbProvider
from controllers import BaseController


class VectorDBFactory:
    def __init__(self, config):
        self.config = config
        self.base_controller = BaseController()

    def create_vector_db(self) -> VectorDBInterface:
        db_config = VectorDBConfig(
            path=self.base_controller.get_database_path(self.config.VECTOR_DB_NAME),
            vector_db_type=self.config.VECTOR_DB_TYPE,
            collection_name=self.config.VECTOR_DB_COLLECTION_NAME,
            embedding_dim=self.config.EMBEDDING_MODEL_SIZE,
            distance=self.config.VECTOR_DB_DISTANCE,
        )

        if db_config.vector_db_type == VectorDBEnum.QDRANT.value:
            return QdrantdbProvider(db_config)
        else:
            raise ValueError(f"Unsupported vector database type: {db_config.vector_db_type}")