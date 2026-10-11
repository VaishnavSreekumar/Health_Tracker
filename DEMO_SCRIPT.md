# HealthTrack — 8-Minute Technical Demo & Interview Walkthrough

This script provides an exact, step-by-step 8-minute demonstration script for technical reviewers and interviewers, based on actual commands, working code, and empirical evaluation metrics.

---

## Demo Timeline Overview (8 Minutes)

| Timestamp | Topic | Focus |
| :--- | :--- | :--- |
| **0:00 – 1:00** | Introduction & Problem Scope | Architecture overview, offline design, zero-credential startup. |
| **1:00 – 2:30** | Backend Foundation & DB Integrity | SQLAlchemy models, timezone normalization, unique constraints, and PII protection. |
| **2:30 – 4:00** | 7-Day Eligibility & Admin REST API | `POST /api/v1/reminders/generate`, idempotency, and transactional savepoints. |
| **4:00 – 6:00** | AI Guardrails & Prompt Injection Defense | Clinical rejection, anti-hallucination, prompt isolation, and two-tier fallback. |
| **6:00 – 7:30** | Evaluation Harness (`evals.run`) | Comparative measurement: 25.0% Baseline vs. 100.0% Guarded. |
| **7:30 – 8:00** | Architectural Trade-offs & Q&A | Honest provider status, heuristic limitations, and production roadmap. |

---

## Detailed Step-by-Step Walkthrough

### Part 1: Introduction & Architecture (0:00 – 1:00)
**Speaker Script**:
> *"HealthTrack is an AI-assisted patient follow-up engine designed for clinical operations coordinators. Rather than simply calling an LLM and hoping for compliant output, HealthTrack implements a reliable engineering pipeline: deterministic eligibility filtering, strict database uniqueness constraints, output guardrails with verified template fallbacks, and an offline evaluation harness that measures safety improvements before and after guardrail activation."*
>
> *"The system is built with FastAPI, SQLAlchemy 2.x, Pydantic, and SQLite, running completely offline without requiring API keys or cloud dependencies."*

---

### Part 2: Backend Foundation & Data Integrity (1:00 – 2:30)
**Action**: Run the core persistence and integrity tests.
```bash
pytest tests/test_models.py tests/test_database.py -v
```
**Talking Points**:
1. **Timezone Normalization**: SQLite lacks native timezone storage. We built `UTCDateTime` (a custom `TypeDecorator`) that normalizes all inputs to UTC and guarantees timezone-aware datetime instances upon retrieval.
2. **Duplicate Outreach Prevention**: Product requirements dictate at most one follow-up reminder per encounter. Rather than relying on race-condition-prone application checks, we enforce `UniqueConstraint("appointment_id")` directly at the database engine level.
3. **PII Protection**: `Patient.__repr__` suppresses patient first names, last names, and email addresses, preventing inadvertent PII leakage in debug logs.

---

### Part 3: 7-Day Eligibility & Administrator REST API (2:30 – 4:00)
**Action**: Launch the API and demonstrate endpoint execution and idempotency.
```bash
# Terminal 1: Launch FastAPI development server
uvicorn app.main:app --port 8000
```
```bash
# Terminal 2: Health check
curl http://127.0.0.1:8000/health
```
*Expected response*:
```json
{"status":"healthy","service":"HealthTrack Follow-Up System","version":"0.1.0","environment":"development"}
```

**Action**: Trigger the administrator reminder generation endpoint:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/reminders/generate \
  -H "Content-Type: application/json" \
  -d '{"window_days": 7}'
```
*Expected response*:
```json
{
  "status": "completed",
  "total_reviewed": 0,
  "reminders_created": 0,
  "reminders_skipped": 0,
  "failures": 0,
  "created_reminder_ids": [],
  "failed_appointment_ids": [],
  "window_days": 7
}
```

**Talking Points**:
- **Eligibility Window**: Encounters strictly in `[reference_time - 7 days, reference_time)`. Lower bound is inclusive; upper bound is exclusive (future encounters are excluded).
- **Idempotency**: Repeated calls review encounters and skip existing reminders (`reminders_skipped`).
- **Savepoint Isolation**: Each draft persistence uses `session.begin_nested()`. If an individual appointment encounters an anomaly, only that savepoint rolls back; sibling appointments continue processing.

---

### Part 4: AI Guardrails & Prompt Injection Defense (4:00 – 6:00)
**Action**: Run the guardrail and personalizer test suites.
```bash
pytest tests/test_guardrails.py tests/test_ai_personalizer.py -v
```

**Talking Points**:
1. **Prompt Isolation**: Server-controlled fixed prompt. User inputs are treated strictly as data tokens. Patient emails, database IDs, and clinical notes are never passed to the LLM.
2. **Multi-tier Output Guardrails (`GuardrailValidator`)**:
   - Rejects clinical diagnoses (`"bronchitis"`) and medication advice (`"take 500mg ibuprofen"`).
   - Rejects hallucinated calendar dates (`"October 25"`), arrival times, and copay claims (`"$45"`).
   - Rejects prompt injection echoes (`"SYSTEM:"`, `"Ignore previous instructions"`) and email leaks.
3. **Two-Tier Fallback Semantics**:
   - If the LLM times out, errors, or produces text rejected by the guardrails, the service automatically falls back to `TemplateMessagePersonalizer`.
   - The fallback message is itself validated through the guardrails before persistence.
   - If both fail, the record fails safely without persisting corrupt text.

---

### Part 5: Evaluation Harness & Comparative Evidence (6:00 – 7:30)
**Action**: Execute the evaluation harness CLI.
```bash
python -m evals.run
```

**Talking Points**:
> *"Most demos show a happy-path message and say 'the AI personalizes it.' An AI engineer's real job is making model output reliable. Here is our empirical measurement loop across 16 deterministic synthetic benchmark cases:"*

**Show Comparison Table on Screen**:
```text
-------------------------------------------------------------------------------------------------------
Evaluation Mode    | Cases   | Passed   | Pass Rate  | Unsafe Accepted  | False Rejections | Fallbacks 
-------------------------------------------------------------------------------------------------------
Baseline           | 16      | 4        | 25.0%      | 9                | 0                | 0         
Guarded (Active)   | 16      | 16       | 100.0%     | 0                | 0                | 12        
-------------------------------------------------------------------------------------------------------
```
- **Baseline (Unguarded)**: Scores **4/16 (25.0%)**. Accepts 9 dangerous outputs (prescriptions, dates, injections) because there is no safety filter.
- **Guarded Mode**: Scores **16/16 (100.0%)**. Intercepts all 12 defects (9 unsafe outputs + 3 provider outages), activates verified clinical templates, and achieves **0 unsafe outputs accepted**.
- **Determinism**: Re-run the command immediately to prove 100% reproducible results without network jitter.

---

### Part 6: Summary & Likely Interviewer Q&A (7:30 – 8:00)

#### Q1: "Why did you enforce duplicate prevention at the database level instead of just checking in Python?"
> **Answer**: *"Application-level checks are prone to race conditions under concurrent worker executions or network retries. By enforcing a `UniqueConstraint('appointment_id')` directly in SQLite, the database engine guarantees referential integrity even if concurrent workers process the same encounter."*

#### Q2: "Are regex and keyword guardrails sufficient for medical safety?"
> **Answer**: *"No, and we explicitly document this limitation in our README. Keyword and pattern matching provide essential defense-in-depth against obvious failures (dosages, medication names, hallucinated dates, prompt injections). However, regex cannot reason about clinical semantics. In production, this would be paired with semantic judge models and licensed physician review."*

#### Q3: "Has a live LLM provider been tested?"
> **Answer**: *"No live LLM API keys were configured or claimed. The architecture provides a clean `LLMClient` protocol adapter, and all tests were verified deterministically using fake provider adapters to guarantee offline reproducibility without network flakiness."*

#### Q4: "Why store reminders as `draft` instead of sending them immediately?"
> **Answer**: *"Separation of concerns. Follow-up generation belongs to the domain service layer. Immediate sending couples message formatting with network transport (Twilio/SendGrid). Storing as `draft` allows administrative review, dead-letter retries, and asynchronous dispatch via a dedicated worker queue."*

#### Q5: "What did the evaluation harness prove that unit tests didn't?"
> **Answer**: *"Unit tests prove code mechanics (e.g. function X returns Y). The eval harness proves system behavior under distribution: comparing unguarded baseline risk against guarded mitigation, measuring false rejection rates, and providing quantitative evidence of reliability."*
