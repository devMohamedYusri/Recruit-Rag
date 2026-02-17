from .ResumeProcessor import ResumeProcessor
from .ScreeningController import ScreeningController


class LLMController(ResumeProcessor, ScreeningController):
    def __init__(self):
        super().__init__()
