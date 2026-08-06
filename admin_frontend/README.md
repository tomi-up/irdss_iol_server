# IRDSS Admin Console

React 18 + Vite control plane for the IRDSS Interoperability Layer gateway.

## Running

```bash
npm install
npm run dev      # http://localhost:5173
```

The dev server proxies `/api/*` to the FastAPI gateway at `http://127.0.0.1:8081`
(see `vite.config.js`), so start the gateway first:

```bash
cd ..
../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8081
```

> The gateway runs **without** `--reload`. Restart it after any backend change.

## Signing in

The console authenticates with an administrator `X-API-Key`. Two credentials are accepted:

1. The gateway root key — the `API_KEY` value in `irdss_project/.env`.
   If that variable is unset, it falls back to `irdss_api_key_default_2026`.
2. Any active row in the `api_keys` table whose `hospital_name` is `SYSTEM_ADMIN`.
   You can mint one from the API Keys page once you are signed in with (1).

Ordinary hospital keys are rejected with HTTP 403 — they can reach their own
`/api/v1/referral` and `/api/v1/hospitals` routes, but never `/api/v1/admin`.

The key is validated against `GET /api/v1/admin/me` before it is written to
`localStorage`, and is re-validated on every page load.

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Network KPIs, 7-day referral volume, status/severity/facility breakdowns |
| `/referrals` | Every referral network-wide, with filters, paging, per-hospital response timeline, and admin force-cancel |
| `/hospitals` | Register/edit/delete facilities and tune the resource fields the AI routing engine reads |
| `/api-keys` | Issue, rotate, deactivate, and revoke hospital credentials |
| `/monitoring` | Gateway uptime, PostgreSQL health, traffic metrics, and the live request log |

## Structure

```
src/
  api/client.js          fetch wrapper; injects X-API-Key, normalizes FastAPI errors
  components/styles.js   shared Tailwind class constants (component-free for Fast Refresh)
  components/ui.jsx      Badge, StatCard, Modal, Alert, Spinner, EmptyState, PageHeader
  components/Layout.jsx  sidebar shell
  context/               AuthProvider + useAuth hook
  hooks/useApiResource   data loading with loading/error state and refresh()
  pages/                 one file per route
  utils/format.js        timestamp/uptime/latency formatters
```

## Notes

- The request log is an **in-memory ring buffer** (1000 entries) held by the FastAPI
  process — it is cleared whenever the gateway restarts. It is not persisted to
  PostgreSQL, so it adds no write load to the referral hot path.
- Plaintext API keys are shown exactly once, at issue/rotate time. The database
  stores only the SHA-256 hash.
