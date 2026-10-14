from pydantic import BaseModel
from typing import List, Optional

#FHIR Name Schema
class FHIRName(BaseModel):
    family: str
    given: List[str]

#Custom AI Constraints
class FHIRExtension(BaseModel):
    url:str
    valueDecimal:Optional[float] = None
    valueString:Optional[str] = None
    valueBoolean:Optional[bool] = None

