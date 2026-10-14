"""FHIR terminology lookup, expansion, validation, and controlled fallback."""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class UnknownValueSetError(ValueError):
    """Raised when a caller requests a ValueSet outside the configured registry."""


class TerminologyServiceError(RuntimeError):
    """Raised when neither Ontoserver nor the controlled fallback can answer."""


@dataclass(frozen=True)
class ValueSetConfig:
    key: str
    url: str
    version: str
    snapshot_filename: str


VALUE_SET_REGISTRY: dict[str, ValueSetConfig] = {
    "diagnosis": ValueSetConfig(
        key="diagnosis",
        url="https://irdss.gov.ph/fhir/ValueSet/referral-diagnosis",
        version="0.1.0",
        snapshot_filename="ValueSet-irdss-referral-diagnosis.json",
    ),
    "chief-complaint": ValueSetConfig(
        key="chief-complaint",
        url="https://irdss.gov.ph/fhir/ValueSet/chief-complaint",
        version="0.1.0",
        snapshot_filename="ValueSet-irdss-chief-complaint.json",
    ),
}


class TerminologyService:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        snapshot_dir: Path | None = None,
        cache_ttl_seconds: int | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("TERMINOLOGY_BASE_URL")
            or "https://tx.fhirlab.net/fhir"
        ).rstrip("/")
        self.snapshot_dir = snapshot_dir or Path(
            os.getenv(
                "TERMINOLOGY_DEFINITION_DIR",
                str(Path(__file__).resolve().parents[2] / "terminology"),
            )
        )
        self.cache_ttl_seconds = cache_ttl_seconds or int(
            os.getenv("TERMINOLOGY_CACHE_TTL_SECONDS", "300")
        )
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("TERMINOLOGY_TIMEOUT_SECONDS", "5")
        )
        self._client = client
        self._cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}

    def get_config(self, value_set_key: str) -> ValueSetConfig:
        try:
            return VALUE_SET_REGISTRY[value_set_key]
        except KeyError as exc:
            raise UnknownValueSetError(
                f"Unsupported ValueSet '{value_set_key}'."
            ) from exc

    async def search(
        self,
        value_set_key: str,
        query: str,
        *,
        count: int = 20,
    ) -> dict[str, Any]:
        config = self.get_config(value_set_key)
        normalized_query = query.strip()
        limited_count = max(1, min(count, 50))
        cache_key = (
            "expand",
            config.url,
            config.version,
            normalized_query.casefold(),
            limited_count,
        )
        cached = self._get_cached(cache_key)
        if cached is not None:
            return {**cached, "source": "cache"}

        try:
            payload = await self._request_json(
                "GET",
                "/ValueSet/$expand",
                params={
                    "url": config.url,
                    "valueSetVersion": config.version,
                    "filter": normalized_query,
                    "count": limited_count,
                    "activeOnly": "true",
                },
            )
            concepts = self._concepts_from_expansion(payload, limited_count)
            allowed = {(c["system"], c["code"]): c for c in self._snapshot_concepts(config)}
            concepts = [allowed[(c["system"], c["code"])] for c in concepts
                        if (c["system"], c["code"]) in allowed]
            result = self._result(config, concepts, "ontoserver")
        except (httpx.HTTPError, ValueError, TerminologyServiceError):
            concepts = self._search_snapshot(config, normalized_query, limited_count)
            result = self._result(config, concepts, "snapshot")

        self._set_cached(cache_key, result)
        return result

    async def validate_code(
        self,
        value_set_key: str,
        *,
        system: str,
        code: str,
    ) -> dict[str, Any]:
        config = self.get_config(value_set_key)
        match = self._find_snapshot_code(config, system, code)
        if match is None:
            return {"value_set": config.key, "url": config.url, "version": config.version,
                    "valid": False, "system": system, "code": code, "display": None,
                    "message": "Code is outside the configured ValueSet.", "source": "snapshot"}
        cache_key = (
            "validate",
            config.url,
            config.version,
            system,
            code,
        )
        cached = self._get_cached(cache_key)
        if cached is not None:
            return {**cached, "source": "cache"}

        try:
            payload = await self._request_json(
                "GET",
                "/ValueSet/$validate-code",
                params={
                    "url": config.url,
                    "valueSetVersion": config.version,
                    "system": system,
                    "code": code,
                },
            )
            valid = self._parameter_value(payload, "result")
            if payload.get("resourceType") != "Parameters" or not isinstance(valid, bool):
                raise TerminologyServiceError("Invalid terminology validation response.")
            display = self._parameter_value(payload, "display")
            if valid:
                display = match["display"]
            if valid and not display:
                match = self._find_snapshot_code(config, system, code)
                display = match["display"] if match else None
                if not display:
                    raise TerminologyServiceError("Validated code has no display label.")
            message = self._parameter_value(payload, "message")
            source = "ontoserver"
        except (httpx.HTTPError, ValueError, TerminologyServiceError):
            match = self._find_snapshot_code(config, system, code)
            valid = match is not None
            display = match.get("display") if match else None
            message = None if valid else "Code is outside the configured ValueSet."
            source = "snapshot"

        result = {
            "value_set": config.key,
            "url": config.url,
            "version": config.version,
            "valid": valid,
            "system": system,
            "code": code,
            "display": display,
            "message": message,
            "source": source,
        }
        self._set_cached(cache_key, result)
        return result

    async def lookup_code(self, *, system: str, code: str) -> dict[str, Any]:
        cache_key = ("lookup", system, code)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return {**cached, "source": "cache"}

        try:
            payload = await self._request_json(
                "GET",
                "/CodeSystem/$lookup",
                params={"system": system, "code": code},
            )
            if payload.get("resourceType") != "Parameters" or not self._parameter_value(payload, "display"):
                raise TerminologyServiceError("Invalid terminology lookup response.")
            result = {
                "system": system,
                "code": code,
                "display": self._parameter_value(payload, "display"),
                "found": True,
                "source": "ontoserver",
            }
        except (httpx.HTTPError, ValueError, TerminologyServiceError):
            match = None
            for config in VALUE_SET_REGISTRY.values():
                match = self._find_snapshot_code(config, system, code)
                if match:
                    break
            result = {
                "system": system,
                "code": code,
                "display": match.get("display") if match else None,
                "found": match is not None,
                "source": "snapshot",
            }

        self._set_cached(cache_key, result)
        return result

    async def _request_json(
        self, method: str, path: str, *, params: dict[str, Any],
    ) -> dict[str, Any]:
        # One bounded retry for transient failures, then controlled fallback.
        # Missing ValueSets and negative validation results are not retried.
        for attempt in range(2):
            try:
                return await self._request_once(method, path, params=params)
            except httpx.HTTPStatusError as exc:
                if attempt or exc.response.status_code not in {502, 503, 504}:
                    raise
            except httpx.TransportError:
                if attempt:
                    raise
        raise TerminologyServiceError("Terminology request failed.")

    async def _request_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.request(method, self.base_url + path, params=params)
        else:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(method, self.base_url + path, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TerminologyServiceError("Terminology server returned invalid JSON.")
        return payload

    def _load_snapshot(self, config: ValueSetConfig) -> dict[str, Any]:
        path = self.snapshot_dir / config.snapshot_filename
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TerminologyServiceError(
                f"Controlled terminology snapshot is unavailable for {config.key}."
            ) from exc
        if payload.get("url") != config.url or payload.get("version") != config.version:
            raise TerminologyServiceError(
                f"Terminology snapshot version mismatch for {config.key}."
            )
        return payload

    def _snapshot_concepts(self, config: ValueSetConfig) -> list[dict[str, str]]:
        payload = self._load_snapshot(config)
        concepts: list[dict[str, str]] = []
        for include in payload.get("compose", {}).get("include", []):
            system = include.get("system")
            for concept in include.get("concept", []):
                if system and concept.get("code") and concept.get("display"):
                    concepts.append(
                        {
                            "system": system,
                            "code": str(concept["code"]),
                            "display": str(concept["display"]),
                        }
                    )
        return concepts

    def _search_snapshot(
        self,
        config: ValueSetConfig,
        query: str,
        count: int,
    ) -> list[dict[str, str]]:
        needle = query.casefold()
        return [
            concept
            for concept in self._snapshot_concepts(config)
            if not needle
            or needle in concept["display"].casefold()
            or needle in concept["code"].casefold()
        ][:count]

    def _find_snapshot_code(
        self,
        config: ValueSetConfig,
        system: str,
        code: str,
    ) -> dict[str, str] | None:
        return next(
            (
                concept
                for concept in self._snapshot_concepts(config)
                if concept["system"] == system and concept["code"] == code
            ),
            None,
        )

    @staticmethod
    def _concepts_from_expansion(
        payload: dict[str, Any],
        count: int,
    ) -> list[dict[str, str]]:
        if payload.get("resourceType") != "ValueSet" or not isinstance(payload.get("expansion"), dict):
            raise TerminologyServiceError("Invalid terminology expansion response.")
        concepts = []
        def visit(items, inherited_system=None):
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise TerminologyServiceError("Invalid terminology expansion concepts.")
            for concept in items:
                system = concept.get("system", inherited_system)
                if (system and concept.get("code") and concept.get("display")
                        and not concept.get("abstract") and not concept.get("inactive")):
                    coding = {"system": str(system), "code": str(concept["code"]),
                              "display": str(concept["display"])}
                    if coding not in concepts:
                        concepts.append(coding)
                visit(concept.get("contains", []), system)
        visit(payload["expansion"].get("contains", []))
        return concepts[:count]

    @staticmethod
    def _parameter_value(payload: dict[str, Any], name: str) -> Any:
        parameters = payload.get("parameter", [])
        if not isinstance(parameters, list) or any(not isinstance(p, dict) for p in parameters):
            raise TerminologyServiceError("Invalid terminology parameters.")
        for parameter in parameters:
            if parameter.get("name") != name:
                continue
            for key, value in parameter.items():
                if key.startswith("value"):
                    return value
        return None

    @staticmethod
    def _result(
        config: ValueSetConfig,
        concepts: list[dict[str, str]],
        source: str,
    ) -> dict[str, Any]:
        return {
            "value_set": config.key,
            "url": config.url,
            "version": config.version,
            "source": source,
            "degraded": source == "snapshot",
            "concepts": concepts,
        }

    def _get_cached(self, key: tuple[Any, ...]) -> dict[str, Any] | None:
        cached = self._cache.get(key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return deepcopy(payload)

    def _set_cached(self, key: tuple[Any, ...], payload: dict[str, Any]) -> None:
        now = time.monotonic()
        for stale in [k for k, (expiry, _) in self._cache.items() if expiry <= now]:
            self._cache.pop(stale, None)
        if key not in self._cache and len(self._cache) >= 256:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (
            now + self.cache_ttl_seconds,
            deepcopy(payload),
        )


terminology_service = TerminologyService()
