# IRDSS System Architecture & Coding Guidelines

## System Overview
This is a multi-tenant Intelligent Referral Decision Support System (IRDSS) and Mock Hospitals HIS.
* **Client/HIS Layer (mock_hospitals):** PHP 8.x, Vanilla JS/jQuery, MySQL (hospital_db). Uses Apache mod_rewrite as a proxy backend.
* **Central IOL Gateway (irdss_project/app):** Python 3.11+, FastAPI (port 8081), SQLAlchemy, PostgreSQL (irdss_db).
* **Admin Layer (irdss_project/admin_frontend):** React 18, Vite.

## Key Endpoints & Flow
* Referrals are packaged as FHIR R4 JSON payloads (Encounter + Patient) by the PHP backend and sent to FastAPI.
* `POST /api/v1/referral/initiate`: Upserts patients, creates referral, triggers AI routing engine (`routing_filter.py`), and broadcasts pending alerts.
* `GET /api/v1/referral/incoming`: Fetches pending requests via proxy.
* `PATCH /api/v1/referral/{referral_id}/respond`: Updates hospital decisions (ACCEPTED/REDIRECTED).

## Strict Security Standards
* **Authentication:** All external HIS nodes must use `X-API-Key` headers. Central DB verifies these against SHA-256 hashes.
* **Data Privacy:** Patient IDs must be encrypted/decrypted at rest in PostgreSQL using AES-256 (`PyCryptodome`).
* **Compliance:** All clinical data transmitted must strictly conform to HL7 FHIR R4 specification.

## Strict Coding Standards & Rules

### General Rules
* **No lazy coding:** Never use placeholders like `// ... rest of the code`. Always write the complete, functional block if requested.
* **Think before writing:** Always briefly outline your logic or architectural approach before generating the code block.
* **Error Handling:** Never swallow errors. Implement strict try/catch blocks and proper logging.
* **Function Documentation:** Every function you write or modify MUST have a concise, one-line explanation comment directly above it explaining its core purpose.

### Tech-Specific Guidelines
* **Python / FastAPI Backend:**
    * Enforce strict PEP 484 type hinting for all functions, arguments, and return types.
    * Always use Pydantic models for request/response validation. No raw dictionaries for data transfer.
    * Ensure all database calls and I/O operations utilize asynchronous patterns (`async`/`await`).
* **React / Vite Admin Frontend:**
    * Use functional components with React Hooks exclusively. No class-based components.
    * Use Tailwind CSS utility classes cleanly. Extract highly repeated class strings into reusable constants.
    * Keep component state local where possible; avoid unnecessary global state.
* **PHP / Frontend Proxy:**
    * Always use prepared statements (PDO) for any direct database queries to prevent SQL injection.
    * Enable `declare(strict_types=1);` at the top of all new PHP files.

### Workflow Directives (`@implement`)
When instructed to implement something and you find `@implement` comments in a file, use the instructions in the comments to implement the requested changes. After implementing, turn the `@implement` comment blocks into proper documentation blocks (drop the `@implement` tag).