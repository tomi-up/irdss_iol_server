from pydantic import BaseModel
from typing import List, Optional
from .fhir_base_schema import FHIRName, FHIRExtension

class FHIRPatient(BaseModel):
    resourceType:str = "Patient"
    id: str
    name: List[FHIRName]
    gender: Optional[str] = "unknown"
    birthDate: Optional[str] = None

    #AI Custom Variable
    extension:List[FHIRExtension]

