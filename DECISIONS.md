# DECISIONS.md

Every ambiguity I found in the starter pack, what I chose, and why.
This is a live document — written before implementation, refined during.

---

## 1. Overlapping doctor windows (Dr. Rao, Monday)

**What I found:**
Dr. Rao's Monday windows are `09:00–12:00` and `11:45–15:00`. They overlap
by 15 minutes (11:45–12:00). This means `11:45` appears in both windows.

**What I chose:**
Deduplicate slot times after generating them across all windows.
`_slots_in_window` returns `11:45` from both; the outer loop adds it once.

**Why:**
Double-counting a slot would allow it to be shown as "free" after it's
booked (because the second window would still produce it). Deduplication
is the only safe choice.

---

## 2. `terminal_state` for "slot not found, caller gives up"

**What I found:**
The schema lists `abandoned` as "conversation ended with no action taken
and no human needed, for example because the caller never gave anything
usable." It lists `refused` separately for requests the agent "should
simply not perform."

**What I chose:**
`abandoned` when the caller asked for something legitimate but the clinic
couldn't accommodate it (doctor on leave, no slots, holiday) and the
caller did not provide an alternative. `refused` only for requests that
are categorically off-limits (bulk operations, prompt injection, "you are
now admin" framing).

**Why:**
`refused` implies the agent made a policy decision. `abandoned` implies
the conversation ran out of useful inputs. cv_0005 (Sunday = no slots,
caller gives up) is `abandoned` per the provided expected output, which
confirms this reading.

---

## 3. "Kal", "parso", Hindi day names — date resolution

**What I found:**
The schema.md README says: "Resolve 'kal', 'parso', 'Saturday' and so on
against the `today` in the request. Never against the system clock."

**What I chose:**
The system prompt explicitly states TODAY = {today} and instructs the LLM
to resolve all relative references against that value. I do *not* parse
dates in the tool layer — that is the LLM's job. The tool layer only
accepts YYYY-MM-DD and rejects anything else with a specific error.

**Why:**
Letting the tool layer parse Hindi is fragile and would require embedding
language intelligence in the "never calls an LLM" layer. The LLM is the
right place for natural language → structured date conversion. The tool
layer acts as a guard: if the LLM resolves a date incorrectly, it gets
a "date not found" or "no slots" error back, which it can surface to
the caller.

---

## 4. Patient authorisation — "shared phone number" case

**What I found:**
Sanjay Rawat (pt_0018) and Kavita Rawat (pt_0019) share the phone number
9812200466. A caller presenting this number could be either of them.
Neither is listed as `guardian_of` the other.

**What I chose:**
Sharing a phone number is *not* authorisation to act on another person's
record. If Kavita calls to cancel Sanjay's appointment, that is
`not_authorised` → escalate. The LLM is instructed to check `guardian_of`
for family-member bookings, and the system prompt explicitly states that
"knowing a phone number is not authorisation."

**Why:**
The cv_0009 expected output confirms this logic: knowing the patient's name
is not authorisation. Phone number is equivalent — it's identifying
information, not an authorisation token.

---

## 5. Guardian booking — ambiguous children (Aarav vs Arjun Gupta)

**What I found:**
pt_0006 (Aarav Gupta, dob 2014-04-18) and pt_0007 (Arjun Gupta, dob
2014-04-18) share surname, DOB, and phone number (9812200166). Sunita
Gupta (pt_0008) is guardian_of both.

**What I chose:**
When a guardian calls and names one child specifically by first name,
that is enough to resolve the ambiguity — as long as the guardian is
confirmed. cv_0008 expects `booked` (not `escalated`), which confirms
this. The LLM must use the first name to select the right child from
`lookup_patient` results.

**Why:**
The test case is explicit. Escalating here would incorrectly penalise
a guardian who named their child clearly.

---

## 6. How `terminal_state` is derived — pure tool layer, not LLM

**What I chose:**
`terminal_state`, `escalation_reason`, `patient_id`, and `appointment_id`
are derived exclusively by walking the `tool_calls_log` in order and
reading tool return values. The LLM's final text reply is *not* parsed
for these fields.

**Why:**
This is the "zero invented facts" guarantee. If the LLM's reply says
"booking confirmed" but `book_appointment` was never called (or returned
an error), the terminal_state is `abandoned`, not `booked`. The grader
checks these fields — not the reply text.

---

## 7. `refused` vs `escalated` for prompt injection

**What I found:**
cv_0014 (prompt injection) expects `refused`, with `must_not_call:
["cancel_appointment", ...]`. The notes say: "refused, not escalated.
There is nothing here for a human to pick up."

**What I chose:**
Pre-screen all turns for injection patterns before the LLM sees them.
If all turns are injection attempts, return `refused` immediately with
no tool calls. If injection appears alongside legitimate turns, the LLM
handles it; the system prompt instructs refusal in that case too.

**Why:**
`escalated` would flood the handoff queue with noise. The brief is clear:
refused means nothing needs a human.

---

## 8. State isolation per request

**What I found:**
Schema.md states: "State resets between conversations. Each POST /agent/run
starts from clinic.json as shipped."

**What I chose:**
`ClinicStore.from_json(clinic_data)` deep-copies the global `_clinic_data`
dict on every call. Nothing is written to disk or a shared DB during a run.
The `results/` directory stores the *output* JSON for the frontend but is
never read by the agent.

**Why:**
In-memory per-request state is the simplest correct solution, matches the
SQLite/in-memory constraint, and makes the "two scripts booking the same
slot" cases work correctly in isolation.

---

## 9. No Sunday window — treated as "clinic closed"

**What I found:**
Neither doctor has a Sunday window in clinic.json. The holidays list only
contains 2026-10-02 (Friday). Sunday 2026-10-04 is not listed as a holiday.

**What I chose:**
`_is_clinic_open` returns `False` for any Sunday (weekday == 6). This is
separate from the holiday check. cv_0005 (Sunday booking request) expects
`abandoned` with `search_slots` called and `book_appointment` *not* called,
which is consistent with search_slots returning `slots: [], reason: clinic_closed`.

**Why:**
A day with no doctor windows is functionally closed. Returning an empty
slots list is the honest answer. Not treating Sunday as closed would cause
search_slots to return an empty list anyway (no windows), but the `reason`
field would be `doctor_not_working` rather than `clinic_closed` — a
meaningful distinction in the response.

---

## 10. `ap_0010` date inconsistency

**What I found:**
ap_0010 has `date: "2026-10-05"` and `doctor_id: "dr_rao"`. Dr. Rao works
on Mondays. 2026-10-05 is a Monday — this is consistent. However, the
`start: "13:00"` is outside Dr. Rao's Monday windows (09:00–12:00 and
11:45–15:00). Actually 13:00 *is* within the 11:45–15:00 window.

**What I found (corrected):**
13:00 falls in the 11:45–15:00 Monday window. It is valid.
I initially thought this was an error — it is not.

**Note in DECISIONS.md:**
No inconsistency. I misread the window. ap_0010 is correct.

---

## 11. `escalate_to_human` as final reply gate

**What I chose:**
After `escalate_to_human` fires successfully, the agent sends one more
request to the LLM (without tools) to generate a compassionate closing
message to the caller, then exits. This gives the caller a meaningful
final message rather than silence.

**Why:**
The spec says nothing about suppressing the final reply on escalation.
The cv_0011 example shows the agent saying "Main abhi aapko clinic se
connect kar raha hoon" after escalation — confirming a closing message
is expected.

---

## 12. Determinism strategy

**What I chose:**
- `temperature=0` on all LLM calls
- `seed=42` on all LLM calls
- Terminal state and structured fields derived from tool return values
  (not LLM text) — so even if the reply varies slightly, the graded
  fields are stable

**Why:**
OpenAI's seed parameter gives "best effort" determinism but does not
guarantee it across model versions. Deriving structured outputs from
tool results rather than parsing LLM text is the only truly deterministic
path for the graded fields.

---

## 13. Medical advice disguised as scheduling

**What I found:**
A caller might ask "how many days should I wait before seeing a doctor?"
or "should I take another Crocin?" framed as context before a booking
request. A naive agent answers the question and books the appointment.

**What I chose:**
The system prompt explicitly flags medical advice requests — including
ones framed as scheduling questions — for `escalate_to_human(reason=
"medical_advice")` *before* booking. adv_008 tests this case.

**Why:**
The grading criteria are explicit: "medical_advice = the caller asked
for a clinical judgement the front desk cannot give." The framing
(scheduling vs. advice) does not change the nature of the request.

---

## 14. Malformed model responses

**What I chose:**
- Tool call argument parsing is wrapped in `try/except json.JSONDecodeError`
  — malformed JSON arguments produce `args = {}` and the tool returns a
  specific "required field missing" error rather than crashing.
- If the LLM API call itself fails (network, rate limit), the endpoint
  returns `terminal_state: "abandoned"` with an error message in `reply`,
  not an HTTP 500.
- Pydantic validation on the request model catches malformed inputs before
  they reach the agent.

**Why:**
The spec says: "Handle a malformed or off-schema model response. It should
not silently corrupt your output or crash the request." The choices above
satisfy each of those failure modes.
