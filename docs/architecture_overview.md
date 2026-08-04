# IRDSS System Architecture & Data Flow Overview

This document provides a comprehensive structural analysis and technical breakdown of the **Intelligent Referral Decision Support System (IRDSS)** and its companion **Mock Hospitals HIS** suite.

---

## 1. System High-Level Architecture Diagram

The system follows a multi-tenant, distributed architecture where individual Hospital Information Systems (HIS) interact with a central Interoperability Layer (IOL) API Gateway.

```mermaid
graph TB
    subgraph Client_Layer ["Client & HIS Layer (PHP Ecosystem)"]
        UI["PHP Web Frontend<br/>(HTML5 / JS App SPA / Leaflet & Mapbox)"]
        PHP_Proxy["PHP Proxy Backend<br/>(Laragon / Apache mod_rewrite)"]
        MYSQL[("MySQL / MariaDB<br/>(hospital_db)<br/>- Patients, Local Accounts")]
    end

    subgraph IOL_Gateway ["Central Interoperability Layer (FastAPI Core)"]
        FastAPI["Python FastAPI Server<br/>(Port 8081 / uvicorn)"]
        Auth["Security Middleware<br/>(SHA-256 API Key Auth & AES-256 Encryption)"]
        AI_Engine["AI Routing Engine<br/>(routing_filter.py)"]
        FHIR_Parser["FHIR R4 Schema Parser<br/>(Encounter & Location)"]
    end

    subgraph Admin_Layer ["Admin Monitoring Layer"]
        Vite_Admin["React Vite Admin Frontend<br/>(System Admin Portal)"]
    end

    subgraph Database_Layer ["Central Storage Layer"]
        POSTGRES[("PostgreSQL<br/>(irdss_db via SQLAlchemy)<br/>- Hospitals, Referrals,<br/>- Patient Records, API Keys")]
    end

    %% Client Interactions
    UI -->|AJAX / Session Auth| PHP_Proxy
    PHP_Proxy <-->|PDO Queries| MYSQL
    PHP_Proxy -->|cURL Proxy / FHIR R4 JSON| FastAPI

    %% FastAPI Internal Flows
    FastAPI --> Auth
    Auth --> FHIR_Parser
    FHIR_Parser --> AI_Engine
    FastAPI <-->|SQLAlchemy ORM| POSTGRES

    %% Admin Interactions
    Vite_Admin -->|REST API + X-API-Key| FastAPI
```

---

## 2. System Subsystems Breakdown

### A. Hospital Information System (HIS) / Mock Hospitals (`mock_hospitals`)
* **Technology Stack**: PHP 8.x, Vanilla JS / jQuery SPA, MySQL (`hospital_db`), Apache (`.htaccess`).
* **Role**: Simulates local hospital EMR/HIS nodes (e.g., St. Jude General Hospital, City Care Medical Center, Metro Health Medical Center).
* **Key Components**:
  * [index.html](file:///c:/laragon/www/mock_hospitals/frontend/index.html) & [app.js](file:///c:/laragon/www/mock_hospitals/frontend/js/app.js): Single-page interface for patient selection, referral dispatch, incoming referral notifications, and capacity management.
  * [config.php](file:///c:/laragon/www/mock_hospitals/backend/config.php): Database connection management and session handling. Defines `IOL_ENDPOINT_URL` (`http://localhost:8081/api/v1/referral/initiate`).
  * [send_referral.php](file:///c:/laragon/www/mock_hospitals/backend/send_referral.php): Fetches local patient demographics from MySQL, builds standard FHIR R4 JSON payloads (`Encounter` + `Patient`), attaches `X-API-Key`, and posts to central IOL.
  * [referral_api.php](file:///c:/laragon/www/mock_hospitals/backend/referral_api.php) & [inventory_api.php](file:///c:/laragon/www/mock_hospitals/backend/inventory_api.php): Transparent reverse proxies using cURL to query FastAPI endpoints (`/api/v1/referral/*` and `/api/v1/hospitals/*`).
  * [.htaccess](file:///c:/laragon/www/mock_hospitals/.htaccess): Rewrite rules routing API path patterns seamlessly to PHP proxy backend endpoints.

### B. Interoperability Layer (IOL) Backend (`irdss_project/app`)
* **Technology Stack**: Python 3.11+, FastAPI, SQLAlchemy, Alembic, PostgreSQL (`irdss_db`), PyCryptodome (AES-256).
* **Role**: Central decision support and data exchange hub connecting regional hospitals across Mindanao.
* **Key Components**:
  * [main.py](file:///c:/IRDSS/irdss_project/app/main.py): Entry point for FastAPI application with CORS middleware configuration.
  * [referral.py](file:///c:/IRDSS/irdss_project/app/routers/referral.py): Core referral workflow engine:
    * `POST /api/v1/referral/initiate`: Validates FHIR payload, encrypts patient FHIR ID with AES-256, upserts patient records, creates a `Referral` entry, and broadcasts alerts (`ReferralResponse` with status `PENDING`) to qualified target facilities.
    * `GET /api/v1/referral/incoming`: Returns pending incoming referral requests for the authenticated hospital, dynamically decrypting patient IDs.
    * `PATCH /api/v1/referral/{referral_id}/respond`: Updates hospital decision (`ACCEPTED` / `REDIRECTED`) with audited turnaround timestamps (`seen_at`, `responded_at`).
    * `GET /api/v1/referral/{referral_id}/recommendations`: Returns matching hospitals sorted by available capacity.
  * [hospitals.py](file:///c:/IRDSS/irdss_project/app/routers/hospitals.py): Handles hospital resource registration (FHIR R4 Location schema) and inventory metrics updates (available beds, equipment, specialist count).
  * [routing_filter.py](file:///c:/IRDSS/irdss_project/app/ai/routing_filter.py): Rule-based decision algorithm targeting candidate receiving facilities based on disease severity.
  * [db_connection.py](file:///c:/IRDSS/irdss_project/app/database/db_connection.py): SQLAlchemy engine and session management connected to PostgreSQL.

### C. Admin Frontend (`irdss_project/admin_frontend`)
* **Technology Stack**: React 18, Vite, ES6+.
* **Role**: Central administrator portal for monitoring regional referral statistics, hospital node health, and API key management.

---

## 3. End-to-End Referral Data Flow

The following sequence diagram outlines how data moves between components during a patient referral lifecycle:

```mermaid
sequenceDiagram
    autonumber
    actor Staff as Hospital Staff (Referring)
    participant Frontend as PHP HIS Frontend
    participant PHP_Backend as PHP HIS Proxy Backend
    participant Local_DB as MySQL (hospital_db)
    participant FastAPI as Python FastAPI (IOL Gateway)
    participant Central_DB as PostgreSQL (irdss_db)
    actor Receiving_Staff as Hospital Staff (Receiving)

    %% Step 1: Authentication & Patient Selection
    Staff->>Frontend: Select patient & submit referral form
    Frontend->>PHP_Backend: POST /backend/send_referral.php (Patient ID, Severity, Geolocation)
    PHP_Backend->>Local_DB: SELECT * FROM patients JOIN hospitals
    Local_DB-->>PHP_Backend: Local Patient Demographics & Hospital API Key

    %% Step 2: FHIR Transformation & IOL Initiation
    PHP_Backend->>PHP_Backend: Package into FHIR R4 JSON (Encounter + Patient extension)
    PHP_Backend->>FastAPI: POST /api/v1/referral/initiate (Header: X-API-Key)
    
    %% Step 3: Central Processing & AI Broadcast
    FastAPI->>Central_DB: Validate SHA-256 API Key
    Central_DB-->>FastAPI: Hospital identity verified
    FastAPI->>FastAPI: AES-256 encrypt Patient ID & calculate Age
    FastAPI->>Central_DB: Upsert PatientRecords & insert Referral (status: CREATED)
    FastAPI->>FastAPI: Execute AI routing_filter (severity matching)
    FastAPI->>Central_DB: Create ReferralResponse entries (status: PENDING) for qualified targets
    FastAPI-->>PHP_Backend: Return Referral Tracking ID (200 OK)
    PHP_Backend-->>Frontend: Display success notification & tracking ID

    %% Step 4: Receiving Hospital Notification & Response
    Receiving_Staff->>FastAPI: GET /api/v1/referral/incoming (Header: X-API-Key) via proxy
    FastAPI->>Central_DB: Query pending alerts & JOIN Referral/PatientRecords
    FastAPI->>FastAPI: Decrypt Patient ID
    Central_DB-->>FastAPI: Incoming referral record
    FastAPI-->>Receiving_Staff: Return referral list JSON
    Receiving_Staff->>FastAPI: PATCH /api/v1/referral/{referral_id}/respond (Decision: ACCEPTED/REDIRECTED)
    FastAPI->>Central_DB: Stamp responded_at timestamp & update ReferralResponse
    FastAPI-->>Receiving_Staff: Confirmation response
```

---

## 4. Key Security & Interoperability Standards

1. **FHIR R4 Schema Standard**: Clinical data transmitted across system boundaries strictly conforms to the HL7 FHIR R4 specification using JSON resources (`Encounter` and `Patient`).
2. **Data Privacy Act / HIPAA Compliance**: Patient identification details are encrypted at rest in the central PostgreSQL database using **AES-256 encryption** (`aes_encrypt` / `aes_decrypt`).
3. **Multi-Tenant API Authentication**: External HIS nodes authenticate to the Interoperability Layer using `X-API-Key` headers. The central server verifies incoming keys against SHA-256 hashes stored in PostgreSQL `api_keys`.
4. **CORS & Proxying**: PHP proxy layers resolve cross-origin policies and encapsulate API key management, keeping client-side JavaScript clean and secure.
