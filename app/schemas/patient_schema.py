from pydantic import BaseModel
from typing import List
from .fhir_base_schema import FHIRName, FHIRExtension

class FHIRPatient(BaseModel):
    resourceType:str = "Patient"
    id: str
    name: List[FHIRName]
    gender: str
    birthDate: str

    #AI Custom Variable
    extension:List[FHIRExtension]

