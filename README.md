# HealthTrack — AI-Driven Patient Follow-Up System

HealthTrack is a backend service designed to automate and personalize post-encounter patient follow-up communications. The intended user is a healthcare clinic operations administrator or care coordinator who manages post-visit outreach, monitors patient engagement, and ensures adherence to discharge and care plans.

> **Status**: **Phase 4: Reproducible AI Evaluation Harness** (Complete).  
> *Note on Delivery*: Follow-up messages are generated and persisted as `draft` records in the database. Actual message transmission (SMS/email transport) is out of scope.  
> *Note on Authentication*: The administrator endpoint operates without production authentication for local assessment and demonstration purposes.

---

## 1. System Scope & Architecture

### Phase 1: Verified Backend Foundation (Complete)
- **Relational Data Model**: SQLAlchemy 2.x declarative models for `Patient`, `Appointment`, and `FollowUpReminder`.
- **Database Architecture**: SQLite engine with explicit table creation, foreign-key constraint enforcement via PRAGMA listeners, and timezone-aware UTC datetime normalization.
- **Data Integrity**: Database-level `UniqueConstraint` guaranteeing a strict one-reminder-per-appointment product policy.
- **API Foundation**: FastAPI application factory with lifecycle management and operational `GET /health` endpoint.

### Phase 2: Reminder Generation Engine (Complete)
- **Appointment Eligibility Service (`get_eligible_appointments`)**:
  - Deterministic lookback interval: Identifies encounters occurring in the previous 7 days (`reference_time - 7 days <= appointment_datetime < reference_time`).
  - Strict Boundaries: Lower bound is inclusive; upper bound is exclusive (strictly excluding future encounters).
  - Timezone Normalization: Guaranteed UTC alignment on query parameters.
- **Message Personalization Interface (`MessagePersonalizer` & `TemplateMessagePersonalizer`)**:
  - Stable protocol interface ready for drop-in LLM providers.
  - Deterministic clinical templates for all five supported `AppointmentType` enum values (`routine_checkup`, `follow_up`, `specialist_consultation`, `annual_physical`, `post_procedure`).
  - Neutral fallback for unknown appointment types or missing patient first names ("there").
- **Batch Generation Service (`ReminderGenerationService`)**:
  - Reviews eligible encounters, formats messages, and creates `FollowUpReminder` records in `draft` status.
  - Idempotency & Duplicate Prevention: Skips appointments that already possess a reminder record; catches concurrent collisions via database uniqueness constraints without crashing.
  - Resilient Error Handling: Utilizes nested transaction savepoints (`session.begin_nested()`) so an individual record failure does not abort or roll back sibling records.

### Phase 3: Administrator REST API & Guardrailed AI Personalization (Complete)
- **Administrator Generation Endpoint (`POST /api/v1/reminders/generate`)**:
  - Triggers batch reminder generation for encounters occurring within the 7-day lookback window.
  - Strongly typed Pydantic models for request options (`window_days`, optional `reference_time` for audits/replay) and responses (`total_reviewed`, `reminders_created`, `reminders_skipped`, `failures`, `created_reminder_ids`).
  - Safe error handling: Sanitized error responses suppressing database internals, stack traces, and patient PII.
- **LLM Provider Abstraction (`LLMClient`, `FakeLLMClient`, `ConfiguredLLMClient`)**:
  - Decoupled adapter interface isolating external LLM providers from business logic.
  - Operates completely offline without API keys using deterministic templates by default.
  - Provider timeouts and network errors handled gracefully without breaking the batch.
- **Output Guardrails (`GuardrailValidator`)**:
  - Length verification (15 to 350 characters).
  - Patient greeting requirement (must contain patient first name or approved neutral greeting).
  - Prohibited clinical patterns: Rejects diagnoses, medication names, prescription instructions, and dosages.
  - Anti-hallucination filter: Rejects unsupported calendar dates, times, dollar figures, and phone numbers.
  - Information leakage filter: Rejects internal database IDs, email addresses, and prompt system leakage (`SYSTEM:`, `Ignore previous instructions`).
- **Prompt Injection Resistance (`GuardrailedAIPersonalizer`)**:
  - Fixed, server-controlled prompts where user data is treated strictly as isolated data attributes.
  - Name inputs are sanitized and stripped of control characters and newline escapes before prompt interpolation.
  - Sensitive patient fields (email, database IDs, notes) are never sent to the LLM.
- **Two-Tier Fallback Semantics**:
  - If the LLM provider fails, times out, or produces text rejected by the guardrails, the service automatically falls back to `TemplateMessagePersonalizer`.
  - The fallback message is itself validated by the guardrails before database persistence.
  - Structured audit logs record outcomes (`outcome=provider_error`, `outcome=guardrail_rejected`, `outcome=fallback_used`) with internal appointment IDs only (zero PII logged).

### Phase 4: Reproducible AI Evaluation Harness (Complete)
- **Offline Evaluation Package (`evals/`)**:
  - Runnable via `python -m evals.run` with zero network access and no API key required.
  - Evaluates **16 deterministic synthetic benchmark cases** across 7 failure-mode categories.
- **Comparative Measurement Loop**:
  - Measures baseline (unguarded) model behavior side-by-side with active guarded behavior on identical cases.
  - Reports actual counts for total cases, valid candidates, rejected candidates, fallback activations, unsafe outputs accepted, and false rejections.
  - Demonstrates a clear, empirical improvement: **25.0% Baseline Pass Rate -> 100.0% Guarded Pass Rate** (0 unsafe outputs accepted).

---

## 2. Project Structure

```text
healthtrack/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory, lifespan, and route mounting
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py  # v1 router aggregator
│   │       └── reminders.py # POST /api/v1/reminders/generate endpoint
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py        # Settings with optional LLM provider config
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py          # Declarative Base and UTCDateTime TypeDecorator
│   │   └── session.py       # Engine creation, PRAGMA listener, sessionmaker, and init_db
│   ├── models/
│   │   ├── __init__.py      # Model registry and exports
│   │   ├── patient.py       # Patient entity (first_name, last_name, email, created_at)
│   │   ├── appointment.py   # Appointment entity (patient_id, appointment_type, appointment_datetime)
│   │   └── reminder.py      # FollowUpReminder entity (appointment_id, message_text, status)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── health.py        # Pydantic schema for health response
│   │   └── reminder.py      # Pydantic schemas for batch reminder requests & responses
│   └── services/
│       ├── __init__.py      # Service exports
│       ├── ai_personalizer.py # GuardrailedAIPersonalizer with prompt injection defense
│       ├── eligibility.py   # Appointment selection within 7-day UTC boundary
│       ├── generator.py     # ReminderGenerationService and GenerationResult
│       ├── guardrails.py    # GuardrailValidator output filter
│       ├── llm_client.py    # LLMClient protocol and adapters (Fake, Configured)
│       └── personalizer.py  # MessagePersonalizer protocol & deterministic templates
├── evals/
│   ├── __init__.py          # Evaluation package exports
│   ├── dataset.py           # 16 deterministic synthetic benchmark cases
│   ├── metrics.py           # Scoring rules, EvaluationSummary, and evaluate_dataset
│   ├── run.py               # CLI runner printing comparison tables (python -m evals.run)
│   └── README.md            # Harness documentation and failure analysis
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Isolated in-memory SQLite fixtures and TestClient
│   ├── test_models.py       # ORM persistence, relationships, cascades, and timezone tests
│   ├── test_database.py     # Unique constraints, foreign-key PRAGMAs, and DB isolation tests
│   ├── test_api.py          # GET /health foundational tests
│   ├── test_api_reminders.py# POST /api/v1/reminders/generate endpoint tests
│   ├── test_eligibility.py  # 7-day window boundary tests (inclusive/exclusive/future/naive)
│   ├── test_personalizer.py # Template personalization, fallback, and PII guardrail tests
│   ├── test_guardrails.py   # Output guardrail validation rules and rejection tests
│   ├── test_ai_personalizer.py # AI personalizer, provider error handling, and prompt injection tests
│   ├── test_generator.py    # Batch generation, idempotency, savepoint error recovery, and log privacy tests
│   └── test_evals.py        # Evaluation dataset, metric arithmetic, and CLI determinism tests
├── requirements.txt         # Explicit version constraints
├── .env.example             # Template environment variables
├── .gitignore               # Comprehensive Python, SQLite, and IDE ignore rules
└── README.md                # System documentation and verification guides
```

---

## 3. Setup & Installation

### 3.1 Prerequisites
- Python 3.11 or newer (tested on Python 3.13).
- `pip` package manager.

### 3.2 Environment Configuration
Clone or navigate to the project directory:
```bash
cd healthtrack
```

Create and activate a virtual environment:
```bash
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate
```

Install dependencies:
```bash
python -m pip install -r requirements.txt
```

Copy the environment template:
```bash
cp .env.example .env
# On Windows PowerShell:
Copy-Item .env.example .env
```

---

## 4. Running the Application & Follow-up Atelier UI

### 4.1 Single-Command Full Stack (API + Built Atelier UI)
The FastAPI server serves both the REST API and the built Follow-up Atelier web application directly:

```bash
uvicorn app.main:app --port 8000
```
Open **`http://127.0.0.1:8000`** in your browser to access the complete Follow-up Atelier interface.

### 4.2 Frontend Hot-Reload Development Server
To develop or customize the React + TypeScript frontend with live reloading:

```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** (automatically proxies `/api` and `/health` requests to `http://localhost:8000`).

To rebuild the production UI bundle:
```bash
cd frontend
npm run build
```

### 4.3 Health Check & Core Endpoints
```bash
curl http://127.0.0.1:8000/health
```

### 4.4 Trigger Batch Reminder Generation
```bash
curl -X POST http://127.0.0.1:8000/api/v1/reminders/generate \
  -H "Content-Type: application/json" \
  -d '{"window_days": 7}'
```

Interactive API documentation:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## 5. Running the AI Evaluation Harness

Run the evaluation harness CLI:

```bash
python -m evals.run
```

### Actual Measured Output
```text
================================================================================
HealthTrack — AI Follow-Up Personalization Evaluation Harness
================================================================================
Evaluating synthetic benchmark cases offline without external API dependencies...

1. SUMMARY COMPARISON:
-------------------------------------------------------------------------------------------------------
Evaluation Mode    | Cases   | Passed   | Pass Rate  | Unsafe Accepted  | False Rejections | Fallbacks 
-------------------------------------------------------------------------------------------------------
Baseline           | 16      | 4        | 25.0%      | 9                | 0                | 0         
Guarded (Active)   | 16      | 16       | 100.0%     | 0                | 0                | 12        
-------------------------------------------------------------------------------------------------------

2. GUARDED MODE CATEGORY BREAKDOWN:
Category                       | Total  | Passed  | Pass Rate  | Unsafe  | Fallbacks 
-------------------------------------------------------------------------------------
clinical_safety                | 3      | 3       | 100.0%     | 0       | 3         
compliant_personalization      | 3      | 3       | 100.0%     | 0       | 0         
date_numeric_hallucination     | 2      | 2       | 100.0%     | 0       | 2         
formatting_bounds              | 2      | 2       | 100.0%     | 0       | 2         
greeting_identity              | 2      | 2       | 100.0%     | 0       | 1         
prompt_injection_leakage       | 2      | 2       | 100.0%     | 0       | 2         
provider_resilience            | 2      | 2       | 100.0%     | 0       | 2         
-------------------------------------------------------------------------------------
```

---

## 6. Running Automated Tests

Run the full 83-test suite:

```bash
pytest -v
```

### Test Suite Verification Matrix (83 Tests Across 12 Modules)
| Test Module | Tests | Focus Area |
| :--- | :---: | :--- |
| `tests/test_api.py` | 4 | System health check, method constraints, and import side-effects. |
| `tests/test_api_product.py` | 4 | Product endpoints: system settings, seed encounters, patient directory, and atelier draft workflow. |
| `tests/test_api_reminders.py` | 7 | `POST /api/v1/reminders/generate` success, empty batches, 7-day filtering, idempotency, parameter validation (422), test isolation, and sanitized 500 error handling. |
| `tests/test_gemini.py` | 10 | Gemini adapter: key configuration, parsing, empty response, auth mapping, rate limits, timeouts, guardrail rejection, compliant acceptance, and opt-in live API integration. |
| `tests/test_database.py` | 8 | Email uniqueness, SQLite PRAGMA foreign keys, duplicate reminder constraint, non-null checks, and database isolation. |
| `tests/test_models.py` | 5 | ORM model persistence, relationship navigation, cascade deletions, PII redaction, and UTC datetime round-tripping. |
| `tests/test_eligibility.py` | 7 | 7-day window boundary tests (inclusive lower bound, exclusive upper bound, past exclusion, future exclusion, ordering, naive normalization). |
| `tests/test_personalizer.py` | 5 | Deterministic templates for all `AppointmentType` enums, name formatting, fallback greetings, and clinical safety. |
| `tests/test_guardrails.py` | 9 | Output validator rules: length boundaries, greeting requirements, clinical language rejections, hallucinated dates/numbers, email/ID leakage, and leaked prompt instructions. |
| `tests/test_ai_personalizer.py` | 9 | AI personalizer: valid output acceptance, length fallback, medical advice fallback, date hallucination fallback, timeout/provider error fallback, prompt injection defense, dual-failure safety, and privacy in log sinks. |
| `tests/test_generator.py` | 6 | Batch generator orchestration: persistence, idempotency, duplicate skipping, savepoint error recovery, concurrency handling, and zero PII logging. |
| `tests/test_evals.py` | 9 | Evaluation harness integrity: dataset structure, metric arithmetic, toy case scoring, deterministic repeat execution, and CLI function execution. |


---

## 7. Known Limitations & Caveats

1. **Heuristic Guardrails != Formal Medical Safety**:
   Regex and keyword pattern matching catch obvious prescription and diagnostic terms, but cannot perform deep semantic reasoning on ambiguous clinical statements.
2. **Synthetic Dataset Scope**:
   The benchmark tests 16 targeted edge cases. Real-world healthcare communication involves complex patient records and varied clinical workflows not fully represented in a synthetic suite.
3. **Draft Storage Only**:
   Reminders are created with status `draft`. Message transmission (SMS/email transport) is out of scope.
4. **Local Evaluation Endpoint**:
   `POST /api/v1/reminders/generate` is designed for evaluation and lacks production authentication.

---

## 8. AI Usage & Transparency

*Note: In accordance with assessment instructions, AI assistance was used for drafting boilerplate scaffolding, regex patterns, and test suites. All results have been verified against active execution evidence.*

- **Assisted Tasks**: Scaffolding evaluation dataclasses, comparison table formatting, pytest fixtures, and regex filters.
- **Verification Performed**: 69 out of 69 automated tests passing locally, live server health check verified, OpenAPI schema routes confirmed, test database isolation validated with zero disk mutations, and evaluation harness executed with identical results across repeated runs.
- **Human Oversight**: Reviewed clinical safety boundaries and confirmed zero PII leakage into log sinks or error payloads.
