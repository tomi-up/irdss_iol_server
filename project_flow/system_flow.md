# IRDSS (Intelligent Referral Decision Support System) - Developer Guide

## Project Overview
The IRDSS project aims to solve the fragmented health information systems (HIS) in Mindanao by establishing an Interoperability Layer (IoL). The system acts as a "universal translator" and "smart router", connecting disparate local systems (e.g., iClinicSys, iHOMIS) without replacing them.

Instead of building a massive standalone app, the core of the project is a secure, API-driven backend that uses Artificial Intelligence to optimize patient navigation, prevent hospital congestion, and minimize patient expenses.

---

## End-to-End System Flow

The referral process follows a strict 5-step data loop:

1. Initiation (The Trigger): A doctor at a Requesting Health Unit initiates a referral natively within their existing Electronic Health Record (EHR) system.
2. Extraction & The Pop-up Interface:
   * This action triggers our custom Embedded Modular Pop-up Interface.
   * The interface automatically fetches existing sociodemographic and clinical records from the local database.
   * The doctor manually inputs missing AI-required constraints (e.g., Patient Salary, Patient Fitness, triaged Disease Severity) into the pop-up.
3. Merging & Standardization: The client-side middleware merges the local DB data and the manual inputs into a single, standardized FHIR JSON object (compliant with PHeReF IG guidelines).
4. Transmission & AI Decision Core:
   * The JSON payload is encrypted via TLS and sent to the IoL FastAPI backend.
   * The IoL decrypts and stores data securely in the PostgreSQL database using AES.
   * The AI kicks in:
     * PSO (Particle Swarm Optimization): Checks real-time hospital inventories (beds, equipment, specialists) in the database to calculate capacities and minimize waiting times.
     * FCM (Fuzzy C-Means): Scores patient constraints against hospital characteristics to find the optimal match.
5. Feedback Loop (Accept/Redirect):
   * The IoL sends a notification payload to potential Receiving Units (e.g., SPMC).
   * The receiving doctor clicks Accept or Redirect on their embedded dashboard.
   * The AI ranks the accepting hospitals and sends the final optimized list back to the requesting doctor for the final decision.

---

## Technical Requirements & Standards

### Core Technologies
* Frontend: Vanilla JavaScript, HTML/CSS (Tailwind CSS suggested), SweetAlert2 for UI feedback.
* Backend: FastAPI (Python) for building the IoL API integration gateway.
* Database (PostgreSQL): A robust relational database chosen to act as the central "processed data lake", highly capable of handling the strict FHIR JSON payloads and dynamic hospital logistics required by the AI.
* Concurrency: FastAPI BackgroundTasks to handle heavy AI mathematical processing without blocking HTTP requests.

### Data Standards & Compliance
* FHIR (Fast Healthcare Interoperability Resources): The international standard data structure (JSON) required for the interoperability layer.
* PHeReF IG (Philippine eReferral Implementation Guide): The localized Philippine blueprint dictating how FHIR payloads must be formatted.
* Data Privacy Act / Security: Must implement RBAC (Role-Based Access Control) via JWTs, Multi-Factor Authentication (MFA), TLS (HTTPS) for data in transit, and AES for data at rest inside the database.

---

## Architecture: Files and Modules Needed

To organize the development, the project should be split into the following modular directories and files:

### A. Frontend Modules (Embedded Interfaces)
* `frontend/referral_initiator.html`: The user-friendly pop-up interface for the requesting doctor. Contains fields for Patient Age (read-only), Salary, Severity, Location, and Fitness.
* `frontend/receiving_dashboard.html`: The embedded dashboard notification for apex hospitals featuring the Accept and Redirect toggle actions.
* `frontend/assets/js/fhir_mapper.js`: The client-side logic that merges the local DB data with the manual inputs and formats it into the strict FHIR JSON payload before sending the POST request.

### B. Backend API Gateway (FastAPI)
* `backend/main.py`: The core FastAPI application instance and router configurations.
* `backend/api/routes/referral.py`: The endpoints that existing EMRs will call (e.g., `POST /api/v1/referral/initiate` and `POST /api/v1/referral/response`).
* `backend/api/auth/security.py`: JWT validation, RBAC enforcement, and AES encryption logic.

### C. Data Validation (Pydantic & FHIR)
* `backend/schemas/fhir_models.py`: Strict Pydantic classes representing the FHIR standard. This ensures the API automatically rejects malformed data payloads before they touch the AI. Includes schemas for `Patient`, `Encounter`, and custom `Extensions` (for Salary/Fitness).

### D. The AI Decision Core
* `backend/ai_core/pso_optimizer.py`: The Particle Swarm Optimization script. Needs functions to parse the hospital resource database (beds, medical professionals) and calculate the optimal daily referral capacity for $n$ hospitals.
* `backend/ai_core/fcm_clustering.py`: The Fuzzy C-Means clustering script. Includes the Virtual Patient Moving Strategy (VPMS) to match patient characteristics matrix (salary, severity) against the hospital features matrix.
* `backend/ai_core/orchestrator.py`: The background task runner that sequences the FCM and PSO models once a batch of referral data is ingested.

### E. Database Architecture (PostgreSQL)
The PostgreSQL database serves as the IoL's "processed data lake". It will require distinct schemas to manage two primary data models:
* Schema 1: Patient Design Matrix (FHIR Inputs): Designed to handle the international FHIR JSON payloads, storing characteristics like Patient Age, Salary, Severity, Location, and Fitness.
* Schema 2: Hospital Features Matrix (Inventory): A dynamic schema tracking the logistical resources of all network hospitals. The AI queries this table for available hospital beds, emergency equipment, communication systems, specialized medical professionals, and hospital level.
* Server Hosting Locations: The database will not require paid cloud hosting. The main server will be deployed on the Data Commons' Satellite Server at UP Mindanao, with a secure backup server located at Data Commons' Main server at UP Diliman to prevent data loss during emergencies.

---

## Development Phasing (What to focus on first)

This is a 3-year project, so do not attempt to build the final AI algorithms immediately.
1. Phase 1 (The Gateway & Database): Focus strictly on the FastAPI endpoints, setting up PostgreSQL, Pydantic data validation (FHIR standardization), and JWT security. Ensure `main.py` can receive and safely store a payload.
2. Phase 2 (The Interface): Build the lightweight frontend pop-up modules (`referral_initiator.html`) that can seamlessly trigger the API.
3. Phase 3 (The Brains): Once the data lake is securely gathering standardized FHIR data, the AI/ML specialists will integrate the `pso_optimizer.py` and `fcm_clustering.py` algorithms.
