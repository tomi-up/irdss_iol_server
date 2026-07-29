## Phase 1: Core Infrastructure & Security Setup (The Foundation)
Before you can process any health data, you must establish a highly secure, compliant environment to house the "processed data lake" [4].

**1. FastAPI Framework Initialization**
*   Set up the core FastAPI application to serve as the external Application Programming Interface (API) for the Interoperability Layer (IoL) [3, 5]. 
*   Define the base routing structures that external Local Government Unit (LGU) systems will call [3].

**2. Database Architecture (PostgreSQL)**

*   Create the **Hospital Features Matrix** schema: This table must track dynamic, real-time inventory for network hospitals, including available hospital beds, emergency equipment, communication systems, and specialized medical professionals [6-9].
*   Create the **Patient Design Matrix** schema: This table will securely store the incoming patient referral records [9].

**3. Cybersecurity & Compliance Implementation**
*   **Data in Transit:** Configure **Transport Layer Security (TLS)** to encrypt all incoming and outgoing API traffic, preventing eavesdropping between the EHR servers and the IoL [10-12].
*   **Access Control:** Implement **Role-Based Access Control (RBAC)** and **Multi-Factor Authentication (MFA)** using JWTs to restrict endpoint access exclusively to authorized healthcare roles and system administrators [13].
*   **Data at Rest:** Implement **Advanced Encryption Standard (AES)** encryption middleware to safeguard sensitive patient data before it is inserted into the database, strictly complying with the Data Privacy Act [4, 10, 14].

---

## Phase 2: The Universal Translator (Data Standardization Pipeline)
Once the gateway is secure, you must write the logic that catches messy, unstructured local data and formats it into the strict Philippine standards.

**1. Pydantic Validation Schemas**
*   Write strict Pydantic models to enforce the international **Fast Healthcare Interoperability Resources (FHIR)** standards and the localized **PHeReF Implementation Guide (IG)** [14-16].
*   If incoming data from a rural clinic fails to match these structures, your FastAPI endpoints must automatically reject the payload [16].

**2. Custom AI "Extension" Merging**
*   Standard FHIR does not natively track the specific variables required by the project's AI [17]. 
*   You must code the middleware that bundles custom manual inputs from the frontend pop-up interface (e.g., Patient Salary/Out-of-pocket spending limits, Patient Fitness, and triaged Disease Severity) into specific FHIR `extension` arrays within the JSON payload [17-19].

**3. The Ingestion Endpoint**
*   Develop the specific `POST` endpoint (e.g., `/api/v1/referral/initiate`) that the LGU IT teams will configure their systems to hit when a doctor clicks the referral trigger button [3, 20].

---

## Phase 3: The Smart Router (AI Orchestration)
In this phase, you bridge your clean data lake with the mathematical algorithms written by the Modeling and AI/ML Specialists [21, 22]. 

**1. Background Task Orchestration**
*   Because the AI algorithms process large datasets (e.g., sample sizes of up to 5,000) to enhance optimization stability, they cannot run synchronously on the main thread [9]. 
*   Implement FastAPI `BackgroundTasks` to asynchronously trigger the AI processing pipeline only after a payload is validated and securely encrypted [23].

**2. Integrating the AI Scripts**
*   **Particle Swarm Optimization (PSO) Trigger:** Write the backend logic that queries the database for real-time hospital capacities (beds, specialists) and feeds this to the PSO script to identify optimal daily patient referral numbers and minimize waiting times [24-26].
*   **Fuzzy-C Means (FCM) Trigger:** Write the logic that feeds the patient's characteristics (severity, expected expenditure, geographic location) into the FCM script to perfectly match the patient to the most suitable hospital [9, 25, 26].

---

## Phase 4: The Feedback Loop (Receiving Unit Callbacks)
The AI cannot make the final decision alone. You must build the endpoints that communicate with the apex receiving hospitals, like the Southern Philippines Medical Center (SPMC) [27, 28].

**1. Broadcast Notification Endpoint**
*   Develop the system function that sends a secure JSON payload to the identified target hospitals, triggering their embedded dashboard notification [28, 29].

**2. Accept / Redirect Callback Routes**
*   Write specific callback endpoints that listen for responses from the receiving doctors [29]. 
*   **Accept Hook:** When a hospital clicks "Accept", the backend must register their capacity and trigger the PSO algorithm to re-rank the accepting hospitals [28, 29].
*   **Redirect Hook:** When a hospital clicks "Redirect", the backend must instantly recalculate and pass the patient request to the next best alternative [28, 29].
*   Finally, send the optimized, ranked list back to the requesting physician's interface to finalize the referral pathway [28, 30].

---

## Phase 5: Testing & Deployment (Scale-Up)
With the codebase complete, development shifts to real-world deployment in the target sites (South Cotabato and Davao de Oro) [25, 31].

**1. Alpha & Beta Testing**
*   Support internal Alpha testing to uncover bugs, followed by Beta testing with the LGU stakeholders under real-world conditions [25, 32].

**2. API Key Distribution & Integration Support**
*   Distribute the API endpoints and integration snippets to external IT teams [20, 33]. 
*   Provide technical deployment support across the tiered scale-up strategy: offering simple licensing for highly mature systems, and full-stack deployment assistance for low-maturity clinics [34]. 