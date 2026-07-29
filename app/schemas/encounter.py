from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from app.schemas.patient_schema import FHIRPatient


# FHIR Reference Schema (e.g. subject)
class FHIRSubject(BaseModel):
    reference: str = Field(..., example="Patient/P-889900")
    display: Optional[str] = Field(None, example="Maria Santos")


# FHIR Coding Schema
class FHIRCoding(BaseModel):
    system: Optional[str] = Field(None, example="http://snomed.info/sct")
    code: Optional[str] = Field(None, example="233604007")
    display: Optional[str] = Field(None, example="Pneumonia")


# FHIR ReasonCode Schema (CodeableConcept)
class FHIRReasonCode(BaseModel):
    text: str = Field(..., example="Severe Pneumonia requiring respiratory support")
    coding: Optional[List[FHIRCoding]] = None


# REQUEST SCHEMA (What external EMR sends)
class ReferralRequestSchema(BaseModel):
    resourceType: str = Field("Encounter", example="Encounter")
    status: str = Field(..., example="planned")
    subject: FHIRSubject
    reasonCode: List[FHIRReasonCode]
    patient_record: FHIRPatient

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resourceType": "Encounter",
                "status": "planned",
                "subject": {
                    "reference": "Patient/P-889900",
                    "display": "Maria Santos"
                },
                "reasonCode": [
                    {
                        "text": "Severe Pneumonia",
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "233604007",
                                "display": "Pneumonia"
                            }
                        ]
                    }
                ],
                "patient_record": {
                    "resourceType": "Patient",
                    "id": "P-889900",
                    "name": [
                        {
                            "family": "Santos",
                            "given": ["Maria"]
                        }
                    ],
                    "gender": "female",
                    "birthDate": "1985-10-12",
                    "extension": [
                        {
                            "url": "http://irdss.gov.ph/fhir/StructureDefinition/salary",
                            "valueDecimal": 12000.0
                        },
                        {
                            "url": "http://irdss.gov.ph/fhir/StructureDefinition/severity",
                            "valueDecimal": 3.0
                        },
                        {
                            "url": "http://irdss.gov.ph/fhir/StructureDefinition/latitude",
                            "valueDecimal": 7.1907
                        },
                        {
                            "url": "http://irdss.gov.ph/fhir/StructureDefinition/longitude",
                            "valueDecimal": 125.4553
                        }
                    ]
                }
            }
        }
    )


# RESPONSE SCHEMA
class ReferralResponseSchema(BaseModel):
    status: str
    message: str
    referral_tracking_id: str