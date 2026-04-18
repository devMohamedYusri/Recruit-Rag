from .BaseController import BaseController
import os

class ProjectController(BaseController):
    """Controller for managing project-specific logic and assets."""
    def __init__(self):
        super().__init__()

    def get_project_asset_path(self, project_id: str) -> str:
        """Returns the filesystem path for project assets, creating it if missing."""
        project_asset_path = os.path.join(self.assets_dir, project_id)
        os.makedirs(project_asset_path, exist_ok=True)
        return project_asset_path
