from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional

# FHIR Position Schema (Geographic Coordinates)
class FHIRLocationPosition(BaseModel):
    latitude: float = Field(..., example=7.0731)
    longitude: float = Field(..., example=125.6128)

# FHIR Extension Schema for custom hospital resource metrics
class FHIRLocationExtension(BaseModel):
    url: str
    valueDecimal: Optional[float] = None
    valueInteger: Optional[int] = None
    valueBoolean: Optional[bool] = None
    valueString: Optional[str] = None

# FHIR R4 Location Schema for Hospital Resource Updates
class FHIRHospitalLocationRequest(BaseModel):
    resourceType: str = Field("Location", example="Location")
    id: Optional[str] = Field(None, example="HOSP-SPMC-001")
    name: str = Field(..., example="Southern Philippines Medical Center")
    status: Optional[str] = Field("active", example="active")
    position: Optional[FHIRLocationPosition] = None
    extension: Optional[List[FHIRLocationExtension]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resourceType": "Location",
                "id": "HOSP-SPMC-001",
                "name": "Southern Philippines Medical Center",
                "status": "active",
                "position": {
                    "latitude": 7.0731,
                    "longitude": 125.6128
                },
                "extension": [
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/hospital_level",
                        "valueString": "Level 3"
                    },
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/hospital_environment",
                        "valueString": "Urban"
                    },
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/available_beds",
                        "valueInteger": 150
                    },
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/emergency_equipment",
                        "valueBoolean": True
                    },
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/medical_equipment",
                        "valueBoolean": True
                    },
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/communication_systems",
                        "valueBoolean": True
                    },
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/medical_specialists_count",
                        "valueInteger": 45
                    }
                ]
            }
        }
    )

# Simplified payload for quick inventory updates
class HospitalInventoryUpdatePayload(BaseModel):
    available_beds: Optional[int] = Field(None, example=120)
    emergency_equipment: Optional[bool] = Field(None, example=True)
    medical_equipment: Optional[bool] = Field(None, example=True)
    communication_systems: Optional[bool] = Field(None, example=True)
    medical_specialists_count: Optional[int] = Field(None, example=40)
    hospital_level: Optional[str] = Field(None, example="Level 3")
    hospital_environment: Optional[str] = Field(None, example="Urban")
    latitude: Optional[float] = Field(None, example=7.0731)
    longitude: Optional[float] = Field(None, example=125.6128)

# Standard Hospital Detail Schema
class HospitalDetailSchema(BaseModel):
    id: int
    hospital_name: str
    hospital_level: Optional[str] = None
    hospital_environment: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    available_beds: Optional[int] = 0
    emergency_equipment: Optional[bool] = False
    medical_equipment: Optional[bool] = False
    communication_systems: Optional[bool] = False
    medical_specialists_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)

# Standard Response Schema
class HospitalResourceResponse(BaseModel):
    status: str
    message: str
    hospital: HospitalDetailSchema
