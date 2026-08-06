from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from app.schemas.patient_schema import FHIRPatient
from datetime import datetime


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
    referral_id: Optional[str] = None


class IncomingReferralSchema(BaseModel):
    """
    Pydantic schema to format the outgoing list of active referral alerts
    for receiving hospital dashboards [cite: 561].
    """
    id: int
    referral_id: str
    hospital_name: str
    response_status: str  # e.g., "PENDING", "SEEN" [cite: 191]
    seen_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None

    # Crucial: Enables Pydantic to read SQLAlchemy ORM models directly [cite: 35]
    model_config = ConfigDict(from_attributes=True)

class IncomingReferralDetailsSchema(IncomingReferralSchema):
    """
    Combines your transactional alert fields with the referenced
    clinical variables on-the-fly for the receiving doctor's modal [cite: 199].
    """
    # Dynamic fields resolved relational-style (never stored in responses table!)
    referring_facility: str
    disease_severity: str
    patient_id: str
    patient_age: int
    patient_gender: str
    clinical_reason: Optional[str] = "None"
    patient_latitude: Optional[float] = None
    patient_longitude: Optional[float] = None
    hospital_latitude: Optional[float] = None
    hospital_longitude: Optional[float] = None
    referring_facility_latitude: Optional[float] = None
    referring_facility_longitude: Optional[float] = None


class ResponsePayloadSchema(BaseModel):
    """
    Pydantic schema to validate the decision body sent by the receiving doctor [cite: 563].
    Must be either "ACCEPTED" or "REDIRECTED" [cite: 191].
    """
    decision: str


class FinalizeReferralSchema(BaseModel):
    """
    Pydantic schema for the referring doctor's final destination choice, locking in
    the patient's clinical pathway among the hospitals that accepted the referral.
    """
    hospital_name: str