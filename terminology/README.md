# IRDSS Terminology Runtime Snapshots

These versioned ValueSet files are the controlled fallback used by the central
IRDSS terminology service when Ontoserver is unavailable. They must remain
aligned with the Phase 1 source artifacts in the Mock Hospital repository.

Runtime configuration:

- `TERMINOLOGY_BASE_URL` defaults to `https://tx.fhirlab.net/fhir`.
- `TERMINOLOGY_CACHE_TTL_SECONDS` defaults to `300` seconds.
- `TERMINOLOGY_TIMEOUT_SECONDS` defaults to `5` seconds.
- `TERMINOLOGY_DEFINITION_DIR` can override this snapshot directory.

Cache keys include the canonical ValueSet URL and version. An unsupported
ValueSet key is rejected rather than forwarded as an arbitrary remote URL.
