import unittest
from unittest.mock import patch
from pathlib import Path

import httpx

from app.services.terminology_service import TerminologyService


SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "terminology"


class TerminologyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_versioned_expansion_and_cache(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.url.params["valueSetVersion"], "0.1.0")
            return httpx.Response(
                200,
                json={
                    "resourceType": "ValueSet",
                    "expansion": {
                        "contains": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "233604007",
                                "display": "Pneumonia",
                            }
                        ]
                    },
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = TerminologyService(
                base_url="https://terminology.example/fhir",
                snapshot_dir=SNAPSHOT_DIR,
                cache_ttl_seconds=60,
                client=client,
            )
            first = await service.search("diagnosis", "pneu")
            second = await service.search("diagnosis", "pneu")

        self.assertEqual(first["source"], "ontoserver")
        self.assertEqual(second["source"], "cache")
        self.assertEqual(first["concepts"][0]["code"], "233604007")
        self.assertEqual(len(requests), 1)

    async def test_search_falls_back_to_controlled_snapshot(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"resourceType": "OperationOutcome"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = TerminologyService(
                base_url="https://terminology.example/fhir",
                snapshot_dir=SNAPSHOT_DIR,
                client=client,
            )
            result = await service.search("chief-complaint", "head")

        self.assertEqual(result["source"], "snapshot")
        self.assertEqual(
            result["concepts"],
            [
                {
                    "system": "http://snomed.info/sct",
                    "code": "25064002",
                    "display": "Headache",
                }
            ],
        )

    async def test_validate_rejects_code_outside_configured_value_set(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            service = TerminologyService(
                base_url="https://terminology.example/fhir",
                snapshot_dir=SNAPSHOT_DIR,
                client=client,
            )
            valid = await service.validate_code(
                "diagnosis",
                system="http://snomed.info/sct",
                code="233604007",
            )
            invalid = await service.validate_code(
                "diagnosis",
                system="http://snomed.info/sct",
                code="25064002",
            )

        self.assertTrue(valid["valid"])
        self.assertEqual(valid["display"], "Pneumonia")
        self.assertFalse(invalid["valid"])
        self.assertIn("outside", invalid["message"])

    async def test_malformed_success_responses_use_snapshot(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"resourceType": "OperationOutcome"}))) as client:
            service = TerminologyService(snapshot_dir=SNAPSHOT_DIR, client=client)
            self.assertEqual((await service.search("diagnosis", "pneu"))["source"], "snapshot")
            result = await service.validate_code("diagnosis", system="http://snomed.info/sct", code="233604007")
            self.assertTrue(result["valid"])
            self.assertEqual(result["source"], "snapshot")
            self.assertEqual((await service.lookup_code(system="http://snomed.info/sct", code="233604007"))["display"], "Pneumonia")

    async def test_nested_expansion_excludes_inactive_and_outside_codes(self):
        payload = {"resourceType": "ValueSet", "expansion": {"contains": [
            {"system": "http://snomed.info/sct", "abstract": True, "contains": [
                {"code": "233604007", "display": "Pneumonia"},
                {"code": "195967001", "display": "Asthma", "inactive": True},
                {"code": "25064002", "display": "Headache"}]}]}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=payload))) as client:
            service = TerminologyService(snapshot_dir=SNAPSHOT_DIR, client=client)
            result = await service.search("diagnosis", "")
        self.assertEqual([c["code"] for c in result["concepts"]], ["233604007"])

    async def test_cache_expiry_and_mutation_isolation(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(503)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TerminologyService(snapshot_dir=SNAPSHOT_DIR, cache_ttl_seconds=10, client=client)
            with patch('app.services.terminology_service.time.monotonic', return_value=100):
                first = await service.search("diagnosis", "pneu")
                first["concepts"][0]["display"] = "tampered"
                cached = await service.search("diagnosis", "pneu")
                self.assertEqual(cached["concepts"][0]["display"], "Pneumonia")
                self.assertTrue(cached["degraded"])
            with patch('app.services.terminology_service.time.monotonic', return_value=111):
                await service.search("diagnosis", "pneu")
        self.assertEqual(len(requests), 4)  # initial request + one retry per expansion

    async def test_transient_retry_is_bounded(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TerminologyService(snapshot_dir=SNAPSHOT_DIR, client=client)
            result = await service.search("diagnosis", "pneu")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["source"], "snapshot")


if __name__ == "__main__":
    unittest.main()
