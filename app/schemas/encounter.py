from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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

    @field_validator("reasonCode")
    @classmethod
    def validate_reason_codes(cls, reasons: List[FHIRReasonCode]) -> List[FHIRReasonCode]:
        if not 1 <= len(reasons) <= 4:
            raise ValueError("reasonCode must contain one primary reason and at most three additional reasons")
        labels = [reason.text.strip().casefold() for reason in reasons]
        if any(not label for label in labels):
            raise ValueError("referral reason text cannot be empty")
        if any(len(reason.text.strip()) > 255 for reason in reasons):
            raise ValueError("referral reason text cannot exceed 255 characters")
        if len(labels) != len(set(labels)):
            raise ValueError("referral reasons must be unique")
        return reasons

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
    created_at: Optional[datetime] = None
    referring_facility: str
    disease_severity: str
    patient_id: str
    patient_age: int
    patient_age_months: Optional[int] = None
    patient_age_days: Optional[int] = None
    patient_gender: str
    clinical_reason: Optional[str] = "None"
    referral_reasons: List[dict] = Field(default_factory=list)
    consent_status: Optional[str] = None
    consent_method: Optional[str] = None
    diagnosis: Optional[str] = None
    chief_complaint: Optional[str] = None
    is_pwd: bool = False
    is_pregnant: bool = False
    is_senior_citizen: bool = False
    has_allergy: bool = False
    allergy_details: Optional[str] = None
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
    redirect_reason_code: Optional[str] = None
    redirect_reason_text: Optional[str] = None

    @model_validator(mode="after")
    def validate_redirect_reason(self):
        self.decision = self.decision.strip().upper()
        allowed_decisions = {"ACCEPTED", "REDIRECTED"}
        if self.decision not in allowed_decisions:
            raise ValueError("decision must be ACCEPTED or REDIRECTED")

        allowed_reasons = {
            "NO_AVAILABLE_BED",
            "SPECIALIST_UNAVAILABLE",
            "SERVICE_UNAVAILABLE",
            "EQUIPMENT_UNAVAILABLE",
            "OUTSIDE_CAPABILITY",
            "TEMPORARY_CLOSURE",
            "OTHER",
        }
        if self.decision == "REDIRECTED":
            self.redirect_reason_code = (self.redirect_reason_code or "").strip().upper()
            self.redirect_reason_text = (self.redirect_reason_text or "").strip() or None
            if self.redirect_reason_code not in allowed_reasons:
                raise ValueError("a valid redirect_reason_code is required when redirecting")
            if self.redirect_reason_code == "OTHER" and not self.redirect_reason_text:
                raise ValueError("redirect_reason_text is required when redirect_reason_code is OTHER")
        else:
            self.redirect_reason_code = None
            self.redirect_reason_text = None
        return self


class FinalizeReferralSchema(BaseModel):
    """
    Pydantic schema for the referring doctor's final destination choice, locking in
    the patient's clinical pathway among the hospitals that accepted the referral.
    """
    hospital_name: str


class ArriveReferralSchema(BaseModel):
    """
    Optional vitals the receiving facility captures at the moment the patient
    physically arrives -- distinct from the referring facility's vital_* readings
    taken at referral time, since a patient's condition can change in transport.
    All fields optional: marking arrival must never be blocked on filling this in.
    """
    vital_bp: Optional[str] = None
    vital_hr: Optional[str] = None
    vital_rr: Optional[str] = None
    vital_temp_c: Optional[str] = None
    vital_o2sat: Optional[str] = None


DEPARTURE_OUTCOMES = ("DISCHARGED", "TRANSFERRED", "DECEASED", "LEFT_AMA")


class DepartReferralSchema(BaseModel):
    """
    Marks the end of the receiving facility's episode of care for this patient, so
    the original referring hospital's tracker doesn't go dark after "Arrived".
    """
    outcome: str
    remarks: Optional[str] = None

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in DEPARTURE_OUTCOMES:
            raise ValueError(f"outcome must be one of {DEPARTURE_OUTCOMES}")
        return upper
