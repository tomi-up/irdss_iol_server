from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional

# FHIR Position Schema (Geographic Coordinates)
class FHIRLocationPosition(BaseModel):
    latitude: float = Field(..., example=7.0731)
    longitude: float = Field(..., example=125.6128)

# FHIR Extension Schema for custom facility resource metrics
class FHIRLocationExtension(BaseModel):
    url: str
    valueDecimal: Optional[float] = None
    valueInteger: Optional[int] = None
    valueBoolean: Optional[bool] = None
    valueString: Optional[str] = None

# FHIR R4 Location Schema for Facility Registration
class FHIRHospitalLocationRequest(BaseModel):
    resourceType: str = Field("Location", example="Location")
    id: Optional[str] = Field(None, example="FAC-000001")
    name: str = Field(..., example="Southern Philippines Medical Center")
    status: Optional[str] = Field("active", example="active")
    position: Optional[FHIRLocationPosition] = None
    extension: Optional[List[FHIRLocationExtension]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resourceType": "Location",
                "id": "FAC-000001",
                "name": "Southern Philippines Medical Center",
                "status": "active",
                "position": {
                    "latitude": 7.0731,
                    "longitude": 125.6128
                },
                "extension": [
                    {
                        "url": "http://irdss.gov.ph/fhir/StructureDefinition/facility_type",
                        "valueString": "Level 3 Hospital"
                    }
                ]
            }
        }
    )

# Standard Facility Detail Schema
class HospitalDetailSchema(BaseModel):
    id: int
    facility_code: Optional[str] = None
    facility_name: str
    facility_type: Optional[str] = None
    ownership: Optional[str] = None
    facility_head: Optional[str] = None
    region: Optional[str] = None
    province: Optional[str] = None
    municipality: Optional[str] = None
    barangay: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    lto_number: Optional[str] = None
    lto_type: Optional[str] = None
    lto_status: Optional[str] = None
    lto_file_path: Optional[str] = None
    facility_status: Optional[str] = "Active"

    @property
    def hospital_name(self) -> str:
        return self.facility_name

    @property
    def hospital_level(self) -> Optional[str]:
        return self.facility_type

    model_config = ConfigDict(from_attributes=True)

# Standard Response Schema
class HospitalResourceResponse(BaseModel):
    status: str
    message: str
    hospital: HospitalDetailSchema
