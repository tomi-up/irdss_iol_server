"""Authenticated IRDSS terminology operations for participating systems."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.routers.referral import get_current_hospital
from app.services.terminology_service import (
    TerminologyServiceError,
    UnknownValueSetError,
    terminology_service,
)


router = APIRouter(prefix="/api/v1/terminology", tags=["Terminology"])


class ValidateCodeRequest(BaseModel):
    value_set: str = Field(min_length=1, max_length=50)
    system: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=100)


def _safe_error(exc: Exception) -> HTTPException:
    if isinstance(exc, UnknownValueSetError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(
        status_code=503,
        detail="Terminology service and controlled fallback are unavailable.",
    )


@router.get("/valuesets/{value_set_key}/search")
async def search_value_set(
    value_set_key: str,
    q: str = Query(default="", max_length=100),
    count: int = Query(default=20, ge=1, le=50),
    _hospital: str = Depends(get_current_hospital),
):
    try:
        return await terminology_service.search(value_set_key, q, count=count)
    except (UnknownValueSetError, TerminologyServiceError) as exc:
        raise _safe_error(exc) from exc


@router.post("/validate-code")
async def validate_code(
    request: ValidateCodeRequest,
    _hospital: str = Depends(get_current_hospital),
):
    try:
        result = await terminology_service.validate_code(
            request.value_set,
            system=request.system,
            code=request.code,
        )
    except (UnknownValueSetError, TerminologyServiceError) as exc:
        raise _safe_error(exc) from exc
    if not result["valid"]:
        raise HTTPException(status_code=422, detail=result)
    return result


@router.get("/lookup")
async def lookup_code(
    system: str = Query(min_length=1, max_length=255),
    code: str = Query(min_length=1, max_length=100),
    _hospital: str = Depends(get_current_hospital),
):
    try:
        result = await terminology_service.lookup_code(system=system, code=code)
    except TerminologyServiceError as exc:
        raise _safe_error(exc) from exc
    if not result["found"]:
        raise HTTPException(status_code=404, detail="Terminology code was not found.")
    return result
