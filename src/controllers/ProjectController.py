from .BaseController import BaseController
import os
class ProjectController(BaseController):
    def __init__(self):
        super().__init__()
    def get_project_asset_path(self,project_id:str)->str:
        project_asset_path=os.path.join(self.assets_dir,project_id)
        if not os.path.exists(project_asset_path):
            os.makedirs(project_asset_path)
        return project_asset_path