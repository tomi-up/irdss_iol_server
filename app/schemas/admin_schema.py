"""
Pydantic contracts for the IRDSS Admin Panel (/api/v1/admin). Every admin endpoint
validates in and out through these models — no raw dictionaries cross the wire.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# GENERIC


class ActionResponse(BaseModel):
    """Uniform envelope for admin mutations that do not return a resource body."""
    status: str = "success"
    message: str


class AdminIdentitySchema(BaseModel):
    """Echoes back the caller's admin identity so the panel can validate a pasted key."""
    hospital_name: str
    is_admin: bool = True
    server_time: datetime


# TWO-FACTOR AUTHENTICATION (TOTP)


class AdminLoginRequest(BaseModel):
    """Phase 1 of admin login: a raw API key, checked before any TOTP prompt."""
    api_key: str


class AdminLoginResponse(BaseModel):
    """Tells the panel which screen to show next: root bypass, TOTP enrollment, or a code prompt."""
    admin_name: str
    totp_enabled: bool
    needs_setup: bool = False
    root: bool = False


class Admin2FASetupResponse(BaseModel):
    """A freshly generated TOTP secret, returned as a scannable URI plus a manual-entry fallback."""
    admin_name: str
    provisioning_uri: str
    secret: str


class Admin2FAVerifyRequest(BaseModel):
    """Phase 2 of admin login: the 6-digit code currently shown in the authenticator app."""
    code: str


class Admin2FAVerifyResponse(BaseModel):
    """A short-lived session token the panel must send instead of the raw key from now on."""
    token: str
    admin_name: str
    totp_enabled: bool


# REFERRAL OVERSIGHT


class AdminReferralResponseRow(BaseModel):
    """A single receiving hospital's decision row inside a referral's response timeline."""
    hospital_name: str
    response_status: str
    seen_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AdminReferralItem(BaseModel):
    """Row shape for the admin 'All Referrals' table."""
    referral_id: str
    patient_id: str
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    referring_facility: str
    receiving_facility: Optional[str] = None
    disease_severity: str
    clinical_reason: Optional[str] = None
    status: str
    broadcast_count: int = 0
    accepted_count: int = 0
    created_at: datetime
    seen_at: Optional[datetime] = None
    evaluated_at: Optional[datetime] = None


class AdminReferralDetail(AdminReferralItem):
    """Full referral record including the per-hospital response timeline."""
    patient_severity: Optional[int] = None
    patient_latitude: Optional[float] = None
    patient_longitude: Optional[float] = None
    responses: List[AdminReferralResponseRow] = Field(default_factory=list)


class AdminReferralListResponse(BaseModel):
    """Paginated envelope for the referrals table."""
    total: int
    page: int
    page_size: int
    items: List[AdminReferralItem]


# DASHBOARD STATISTICS


class StatusCountItem(BaseModel):
    """One slice of a categorical breakdown chart (status, facility, severity)."""
    label: str
    count: int


class DailyVolumeItem(BaseModel):
    """One point on the referral-volume time series."""
    date: str
    count: int


class AdminStatsResponse(BaseModel):
    """Aggregate KPIs rendered on the admin dashboard landing page."""
    total_referrals: int
    referrals_today: int
    referrals_last_7_days: int
    active_referrals: int
    completed_referrals: int
    cancelled_referrals: int
    total_hospitals: int
    total_available_beds: int
    total_api_keys: int
    active_api_keys: int
    avg_response_minutes: Optional[float] = None
    status_breakdown: List[StatusCountItem]
    severity_breakdown: List[StatusCountItem]
    top_referring_facilities: List[StatusCountItem]
    top_receiving_facilities: List[StatusCountItem]
    daily_volume: List[DailyVolumeItem]


# HOSPITAL MANAGEMENT


class AdminHospitalItem(BaseModel):
    """Full hospital resource record as surfaced in the admin hospital manager."""
    id: int
    hospital_name: str
    hospital_level: Optional[str] = None
    hospital_environment: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    available_beds: Optional[int] = None
    emergency_equipment: Optional[bool] = None
    medical_equipment: Optional[bool] = None
    communication_systems: Optional[bool] = None
    medical_specialists_count: Optional[int] = None
    pso_daily_routing_limit: Optional[int] = None
    referrals_accepted_today: Optional[int] = None
    has_api_key: bool = False

    model_config = ConfigDict(from_attributes=True)


class AdminHospitalCreate(BaseModel):
    """Payload for provisioning a brand new hospital node from the admin panel."""
    hospital_name: str = Field(..., min_length=2)
    hospital_level: str = "Level 1"
    hospital_environment: str = "Urban"
    latitude: float = 0.0
    longitude: float = 0.0
    available_beds: int = 0
    emergency_equipment: bool = False
    medical_equipment: bool = False
    communication_systems: bool = False
    medical_specialists_count: int = 0
    pso_daily_routing_limit: int = 5


class AdminHospitalUpdate(BaseModel):
    """Partial update payload; only the fields present are written."""
    hospital_name: Optional[str] = Field(None, min_length=2)
    hospital_level: Optional[str] = None
    hospital_environment: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    available_beds: Optional[int] = None
    emergency_equipment: Optional[bool] = None
    medical_equipment: Optional[bool] = None
    communication_systems: Optional[bool] = None
    medical_specialists_count: Optional[int] = None
    pso_daily_routing_limit: Optional[int] = None
    referrals_accepted_today: Optional[int] = None


# API KEY MANAGEMENT


class AdminApiKeyItem(BaseModel):
    """API key metadata. The raw secret is never returned here — only a masked display form."""
    id: int
    hospital_name: str
    api_key_display: str
    is_active: bool
    created_at: Optional[datetime] = None


class AdminApiKeyCreate(BaseModel):
    """Request to mint a new API key for a hospital (or for SYSTEM_ADMIN)."""
    hospital_name: str = Field(..., min_length=2)


class AdminApiKeyUpdate(BaseModel):
    """Toggle a key's active flag and/or reassign its owning hospital."""
    is_active: Optional[bool] = None
    hospital_name: Optional[str] = Field(None, min_length=2)


class AdminApiKeyIssuedResponse(BaseModel):
    """
    Returned exactly once, at mint/rotate time. `raw_key` is the only moment the
    plaintext secret exists outside the caller — the DB stores only its SHA-256 hash.
    """
    status: str = "success"
    message: str
    raw_key: str
    key: AdminApiKeyItem


# SERVER MONITORING & LOGS


class LogEntrySchema(BaseModel):
    """One buffered HTTP request as shown in the live log viewer."""
    id: int
    timestamp: datetime
    level: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    client_ip: Optional[str] = None
    hospital_name: Optional[str] = None
    error: Optional[str] = None


class LogListResponse(BaseModel):
    """Envelope for the log viewer, including how many entries the buffer holds."""
    buffered_entries: int
    max_entries: int
    items: List[LogEntrySchema]


class EndpointCountItem(BaseModel):
    """Traffic count for a single `METHOD /path` combination."""
    endpoint: str
    count: int


class StatusCodeCountItem(BaseModel):
    """Traffic count for a single HTTP status code."""
    status_code: str
    count: int


class SystemHealthResponse(BaseModel):
    """Live health snapshot: process uptime, DB reachability, and traffic metrics."""
    status: str
    server_started_at: datetime
    uptime_seconds: float
    database_connected: bool
    database_error: Optional[str] = None
    database_latency_ms: Optional[float] = None
    window_minutes: int
    buffered_entries: int
    requests_in_window: int
    errors_in_window: int
    avg_response_ms: float
    slowest_response_ms: float
    lifetime_requests: int
    lifetime_client_errors: int
    lifetime_server_errors: int
    top_endpoints: List[EndpointCountItem]
    status_breakdown: List[StatusCodeCountItem]
    table_counts: dict[str, Any]
