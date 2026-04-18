from typing import Annotated
from pydantic import BeforeValidator, PlainSerializer

PyObjectId = Annotated[
    str, 
    BeforeValidator(str),
    PlainSerializer(lambda x: str(x), return_type=str, when_used='json-unless-none')
]
