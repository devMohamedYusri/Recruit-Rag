from pydantic import BaseModel
from typing import Optional


class JobDescriptionRequest(BaseModel):
    title: str
    description: str
    prompt: Optional[str] = None
    weights: Optional[dict[str, float]] = None
    custom_rubric: Optional[str] = None


class ProcessResumesRequest(BaseModel):
    file_ids: Optional[list[str]] = None
    do_reset: bool = False


class ScreenRequest(BaseModel):
    file_ids: Optional[list[str]] = None
    anonymize: bool = True

