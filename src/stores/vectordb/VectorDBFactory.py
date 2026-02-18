from .VectorDBEnums import VectorDBEnum, VectorDBConfig
from .VectorDBInterface import VectorDBInterface
from .providers.QdrantdbProvider import QdrantdbProvider
import os


class VectorDBFactory:
    def __init__(self, config):
        self.config = config
    def create_vector_db(self) -> VectorDBInterface:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        db_path = os.path.join(base_dir, self.config.DB_DIRECTORY, self.config.VECTOR_DB_NAME)
        if not os.path.exists(db_path):
             os.makedirs(db_path)

        db_config = VectorDBConfig(
            path=db_path,
            vector_db_type=self.config.VECTOR_DB_TYPE,
            collection_name=self.config.VECTOR_DB_COLLECTION_NAME,
            embedding_dim=self.config.EMBEDDING_MODEL_SIZE,
            distance=self.config.VECTOR_DB_DISTANCE,
        )

        if db_config.vector_db_type == VectorDBEnum.QDRANT.value:
            return QdrantdbProvider(db_config)
        else:
            raise ValueError(f"Unsupported vector database type: {db_config.vector_db_type}")