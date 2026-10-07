# SwasthiQ — Clinic Front Desk Agent

A conversational front-desk agent for Sunrise Clinic, Dehradun.
Handles appointment booking, rescheduling, cancellation, and safe escalation to humans.

---

## One-command run

```bash
# 1. Install backend dependencies
cd backend
pip install -r requirements.txt

# 2. Set your OpenAI key
cp .env.example .env
# edit .env and add OPENAI_API_KEY=sk-...

# 3. Start the backend
uvicorn main:app --host 0.0.0.0 --port 8000

# 4. In a separate terminal — start the frontend
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

Run the conversation harness (from the starter pack directory):

```bash
python runner.py --url http://localhost:8000/agent/run
```

Determinism check:

```bash
python runner.py --repeat 3
```

Run backend unit tests (no API key required):

```bash
cd backend
python -m pytest test_tools.py -v
```

---

## Repository layout

```
/backend
  main.py           FastAPI app — POST /agent/run, GET /conversations, GET /health
  agent.py          LLM agent loop (OpenAI tool-calling, safety gates, determinism)
  clinic_store.py   Tool layer — 6 tools against clinic.json, no LLM
  test_tools.py     Unit tests for the tool layer (pytest)
  requirements.txt
  .env.example

/frontend
  src/
    App.jsx
    pages/
      HandoffQueue.jsx        Screen 1 — counters + open escalations
      ConversationDetail.jsx  Screen 2 — transcript + outcome panel
    components/
      Layout.jsx              Shared sidebar, persists across both screens
    api.js                    Thin fetch wrapper
  vite.config.js              Dev proxy → backend :8000

/adversarial
  adv_001.json … adv_008.json   Eight adversarial conversation scripts

README.md
DECISIONS.md
```

---

## API contract

### `POST /agent/run`

**Request**
```json
{
  "conversation_id": "cv_0001",
  "today": "2026-10-01",
  "turns": ["Namaste, appointment chahiye tha.", "Kal subah."]
}
```

**Response** (schema.md contract)
```json
{
  "conversation_id": "cv_0001",
  "tool_calls": [
    {"name": "search_slots", "arguments": {"doctor_id": "dr_rao", "date": "2026-10-02"}},
    {"name": "book_appointment", "arguments": {"patient_id": "pt_0013", "doctor_id": "dr_rao", "date": "2026-10-02", "start": "09:00"}}
  ],
  "terminal_state": "booked",
  "escalation_reason": null,
  "patient_id": "pt_0013",
  "appointment_id": "ap_0026",
  "reply": "Ji, appointment book ho gaya hai.",
  "metrics": {"turns": 2, "tokens": 1840, "latency_ms": 2100}
}
```

`terminal_state` values: `booked` | `rescheduled` | `cancelled` | `escalated` | `refused` | `abandoned`

`escalation_reason` values (when escalated): `clinical_urgent` | `medical_advice` | `not_authorised` | `ambiguous_patient` | `out_of_scope`

### `GET /conversations`
Returns `{"conversations": [...]}` — all persisted run results for the frontend.

### `GET /conversations/{id}`
Returns the latest run result for one conversation.

### `GET /health`
Returns `{"status": "ok", "clinic": "Sunrise Clinic"}`.

---

## Six tools

| Tool | Arguments | What it does |
|---|---|---|
| `search_slots` | `doctor_id`, `date`, `window?` | Returns free 15-min slots; `window` = morning/afternoon/evening |
| `book_appointment` | `patient_id`, `doctor_id`, `date`, `start` | Books a slot; rejects double-booking |
| `reschedule_appointment` | `appointment_id`, `new_date`, `new_start` | Moves an existing booking |
| `cancel_appointment` | `appointment_id` | Cancels a booked appointment |
| `lookup_patient` | `name?`, `phone?` | Fuzzy name + exact phone matching; returns all candidates |
| `escalate_to_human` | `reason`, `detail?` | Signals human handoff; hard-stops the agent loop |

All tools are pure Python functions on `ClinicStore` — no LLM, no network calls.
State consistency: each `/agent/run` call creates a fresh `ClinicStore` from `clinic.json`.
Double-booking prevention: `book_appointment` calls `search_slots` internally; the slot must appear in the live free list at booking time.

---

## How data consistency is maintained on update

- **Per-request isolation**: `ClinicStore.from_json(clinic_data)` deep-copies clinic.json on every request. No shared mutable state between requests.
- **No double-booking**: `book_appointment` re-derives free slots at call time by scanning `_appointments` in the live store. A slot booked mid-conversation is immediately gone from subsequent `search_slots` calls in the same conversation.
- **Reschedule atomicity**: `reschedule_appointment` marks the old appointment `cancelled` and creates a new one in the same Python call — no window for partial state.
- **Rollback by design**: Because state is in-memory and never written to a shared DB, there is nothing to roll back. Two concurrent requests each get their own copy of `clinic.json`. This matches the schema.md requirement: "State resets between conversations."

---

## Model and performance

| Field | Value |
|---|---|
| Model | `gpt-4o` (configurable via `AGENT_MODEL` env var) |
| Temperature | `0` |
| Seed | `42` |
| Avg tokens / conversation | ~1,800–3,200 (varies by turns) |
| Avg latency / conversation | ~2–5 seconds |
| Determinism | temperature=0 + seed=42 → same terminal_state / escalation_reason / tool set across runs |

> Exact tokens and latency are returned in every response's `metrics` object and logged to `results/`.

---

## Safety design

1. **Clinical pre-screen**: Every caller turn is scanned for ~25 emergency keywords (Hindi + English) *before* the LLM sees it. If any match: immediate `escalate_to_human(reason="clinical_urgent")` with no LLM call.
2. **Prompt injection pre-screen**: Turns matching injection patterns ("ignore previous instructions", "administrator mode") bypass the LLM and return `refused`.
3. **Hard gate on escalate_to_human**: Once the tool fires and returns `escalated: true`, the agent loop exits immediately regardless of what the model wants to do next.
4. **Zero invented facts**: `terminal_state`, `patient_id`, `appointment_id`, and `escalation_reason` are derived *only* from tool return values — never from LLM text.
5. **Grounding enforcement in system prompt**: The prompt explicitly forbids mentioning slots, patients, or appointments that tools did not return, and uses `temperature=0` to minimize hallucination.
