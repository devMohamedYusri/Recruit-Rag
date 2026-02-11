from utils import Settings,get_settings
import os
import random
import string


class BaseController:
    def __init__(self):
        self.app_settings:Settings=get_settings()
        self.base_dir=os.path.dirname(os.path.dirname(__file__))
        self.assets_dir=os.path.join(self.base_dir,self.app_settings.UPLOAD_DIRECTORY)
    def generate_random_id(self,length=12):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))