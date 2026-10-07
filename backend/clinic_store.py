"""
clinic_store.py — In-memory state for a single /agent/run request.

Each request calls ClinicStore.from_json(clinic_json) to get a fresh snapshot.
Nothing here touches an LLM.  This is the ground truth layer.
"""
from __future__ import annotations

import copy
import json
import pathlib
from datetime import date, datetime, time, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DAYS_SHORT = {
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
    "Fri": 4, "Sat": 5, "Sun": 6,
}


def _parse_time(t: str) -> time:
    return datetime.strptime(t, "%H:%M").time()


def _parse_date(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _slots_in_window(win_start: time, win_end: time, slot_minutes: int) -> list[str]:
    """Return every slot start time (HH:MM) that fits within [win_start, win_end)."""
    slots = []
    current = datetime.combine(date.today(), win_start)
    end_dt = datetime.combine(date.today(), win_end)
    while current < end_dt:
        slot_end = current + timedelta(minutes=slot_minutes)
        if slot_end <= end_dt:
            slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=slot_minutes)
    return slots


# ---------------------------------------------------------------------------
# ClinicStore
# ---------------------------------------------------------------------------

class ClinicStore:
    """Mutable, per-request copy of clinic.json."""

    def __init__(self, data: dict) -> None:
        self._data = data
        self._slot_minutes: int = data["clinic"]["slot_minutes"]
        self._holidays: set[str] = set(data.get("holidays", []))

        # index structures
        self._doctors: dict[str, dict] = {d["id"]: d for d in data["doctors"]}
        self._patients: dict[str, dict] = {p["id"]: p for p in data["patients"]}
        # appointments keyed by id; mutable
        self._appointments: dict[str, dict] = {
            a["id"]: copy.deepcopy(a) for a in data["appointments"]
        }
        # next appointment id counter
        existing_nums = [
            int(aid.split("_")[1]) for aid in self._appointments if "_" in aid
        ]
        self._next_ap_num: int = (max(existing_nums) + 1) if existing_nums else 1

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | pathlib.Path) -> "ClinicStore":
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    @classmethod
    def from_json(cls, data: dict) -> "ClinicStore":
        return cls(copy.deepcopy(data))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _doctor_works(self, doctor_id: str, target_date: date) -> bool:
        """True if the doctor has windows on that weekday and is not on leave."""
        doctor = self._doctors.get(doctor_id)
        if not doctor:
            return False
        date_str = target_date.strftime("%Y-%m-%d")
        if date_str in doctor.get("leave_dates", []):
            return False
        day_abbr = target_date.strftime("%a")  # Mon, Tue …
        windows = [w for w in doctor.get("windows", []) if w["day"] == day_abbr]
        return bool(windows)

    def _is_clinic_open(self, target_date: date) -> bool:
        date_str = target_date.strftime("%Y-%m-%d")
        if date_str in self._holidays:
            return False
        # Sundays: no doctor has a Sunday window in clinic.json — treated as closed
        if target_date.weekday() == 6:
            return False
        return True

    def _booked_starts(self, doctor_id: str, date_str: str) -> set[str]:
        """Return set of start-times already booked for this doctor+date."""
        return {
            a["start"]
            for a in self._appointments.values()
            if a["doctor_id"] == doctor_id
            and a["date"] == date_str
            and a["status"] == "booked"
        }

    def _new_ap_id(self) -> str:
        aid = f"ap_{self._next_ap_num:04d}"
        self._next_ap_num += 1
        return aid

    # ------------------------------------------------------------------
    # Tool: search_slots
    # ------------------------------------------------------------------

    def search_slots(
        self,
        doctor_id: str,
        date: str,
        window: str | None = None,
    ) -> dict[str, Any]:
        """
        Return free 15-minute slots.

        Parameters
        ----------
        doctor_id : e.g. "dr_rao"
        date      : "YYYY-MM-DD"
        window    : optional "morning" | "afternoon" | "evening"
                    morning   = before 12:00
                    afternoon = 12:00–16:00
                    evening   = 16:00+
        """
        if not doctor_id or not date:
            return {"error": "doctor_id and date are required"}

        try:
            target = _parse_date(date)
        except ValueError:
            return {"error": f"Invalid date format '{date}'. Use YYYY-MM-DD."}

        if not self._is_clinic_open(target):
            return {"slots": [], "reason": "clinic_closed"}

        doctor = self._doctors.get(doctor_id)
        if not doctor:
            return {"error": f"Unknown doctor_id '{doctor_id}'"}

        date_str = target.strftime("%Y-%m-%d")
        leave_dates = doctor.get("leave_dates", [])
        if date_str in leave_dates:
            return {"slots": [], "reason": "doctor_on_leave"}

        day_abbr = target.strftime("%a")
        windows = [w for w in doctor["windows"] if w["day"] == day_abbr]
        if not windows:
            return {"slots": [], "reason": "doctor_not_working"}

        booked = self._booked_starts(doctor_id, date_str)

        all_free: list[str] = []
        for w in windows:
            for slot in _slots_in_window(
                _parse_time(w["start"]), _parse_time(w["end"]), self._slot_minutes
            ):
                if slot not in booked:
                    all_free.append(slot)

        # deduplicate while preserving order (overlapping windows possible)
        seen: set[str] = set()
        deduped: list[str] = []
        for s in all_free:
            if s not in seen:
                seen.add(s)
                deduped.append(s)

        # filter by window preference
        if window:
            w_lower = window.lower()
            if w_lower == "morning":
                deduped = [s for s in deduped if _parse_time(s) < time(12, 0)]
            elif w_lower == "afternoon":
                deduped = [
                    s for s in deduped
                    if time(12, 0) <= _parse_time(s) < time(16, 0)
                ]
            elif w_lower == "evening":
                deduped = [s for s in deduped if _parse_time(s) >= time(16, 0)]

        return {
            "doctor_id": doctor_id,
            "date": date_str,
            "slots": deduped,
        }

    # ------------------------------------------------------------------
    # Tool: book_appointment
    # ------------------------------------------------------------------

    def book_appointment(
        self,
        patient_id: str,
        doctor_id: str,
        date: str,
        start: str,
    ) -> dict[str, Any]:
        """Book a slot. Rejects double-booking atomically."""
        for field, val in [("patient_id", patient_id), ("doctor_id", doctor_id),
                           ("date", date), ("start", start)]:
            if not val:
                return {"error": f"'{field}' is required"}

        if patient_id not in self._patients:
            return {"error": f"Unknown patient_id '{patient_id}'"}
        if doctor_id not in self._doctors:
            return {"error": f"Unknown doctor_id '{doctor_id}'"}

        try:
            target = _parse_date(date)
        except ValueError:
            return {"error": f"Invalid date '{date}'. Use YYYY-MM-DD."}

        if not self._is_clinic_open(target):
            return {"error": "Clinic is closed on that date."}

        date_str = target.strftime("%Y-%m-%d")

        # validate start time format
        try:
            start_t = _parse_time(start)
        except ValueError:
            return {"error": f"Invalid start time '{start}'. Use HH:MM."}

        # confirm slot actually exists in the doctor's windows
        free = self.search_slots(doctor_id, date_str)
        if "error" in free:
            return free
        if start not in free["slots"]:
            if free["slots"]:
                return {
                    "error": f"Slot {start} is not available for {doctor_id} on {date_str}. "
                             f"Free slots: {free['slots'][:5]}"
                }
            else:
                return {"error": f"No slots available for {doctor_id} on {date_str}."}

        end_t = (datetime.combine(target, start_t) + timedelta(minutes=self._slot_minutes)).time()
        ap_id = self._new_ap_id()
        self._appointments[ap_id] = {
            "id": ap_id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "date": date_str,
            "start": start,
            "end": end_t.strftime("%H:%M"),
            "status": "booked",
        }
        return {
            "appointment_id": ap_id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "date": date_str,
            "start": start,
            "end": end_t.strftime("%H:%M"),
            "status": "booked",
        }

    # ------------------------------------------------------------------
    # Tool: reschedule_appointment
    # ------------------------------------------------------------------

    def reschedule_appointment(
        self,
        appointment_id: str,
        new_date: str,
        new_start: str,
    ) -> dict[str, Any]:
        """Move an existing appointment to a new date/time."""
        for field, val in [("appointment_id", appointment_id),
                           ("new_date", new_date), ("new_start", new_start)]:
            if not val:
                return {"error": f"'{field}' is required"}

        ap = self._appointments.get(appointment_id)
        if not ap:
            return {"error": f"Appointment '{appointment_id}' not found."}
        if ap["status"] != "booked":
            return {"error": f"Appointment '{appointment_id}' is not in booked state."}

        try:
            target = _parse_date(new_date)
        except ValueError:
            return {"error": f"Invalid date '{new_date}'. Use YYYY-MM-DD."}

        try:
            _parse_time(new_start)
        except ValueError:
            return {"error": f"Invalid start time '{new_start}'. Use HH:MM."}

        new_date_str = target.strftime("%Y-%m-%d")
        free = self.search_slots(ap["doctor_id"], new_date_str)
        if "error" in free:
            return free
        if new_start not in free["slots"]:
            if free["slots"]:
                return {
                    "error": f"Slot {new_start} is not available on {new_date_str}. "
                             f"Free slots: {free['slots'][:5]}"
                }
            else:
                return {"error": f"No slots available on {new_date_str}."}

        # Perform move: cancel old, create new
        old_start = ap["start"]
        old_date = ap["date"]
        start_t = _parse_time(new_start)
        end_t = (datetime.combine(target, start_t) + timedelta(minutes=self._slot_minutes)).time()

        ap["status"] = "cancelled"

        new_ap_id = self._new_ap_id()
        self._appointments[new_ap_id] = {
            "id": new_ap_id,
            "patient_id": ap["patient_id"],
            "doctor_id": ap["doctor_id"],
            "date": new_date_str,
            "start": new_start,
            "end": end_t.strftime("%H:%M"),
            "status": "booked",
        }
        return {
            "appointment_id": new_ap_id,
            "previous_appointment_id": appointment_id,
            "patient_id": ap["patient_id"],
            "doctor_id": ap["doctor_id"],
            "old_date": old_date,
            "old_start": old_start,
            "new_date": new_date_str,
            "new_start": new_start,
            "new_end": end_t.strftime("%H:%M"),
            "status": "booked",
        }

    # ------------------------------------------------------------------
    # Tool: cancel_appointment
    # ------------------------------------------------------------------

    def cancel_appointment(self, appointment_id: str) -> dict[str, Any]:
        """Cancel an appointment by id."""
        if not appointment_id:
            return {"error": "'appointment_id' is required"}

        ap = self._appointments.get(appointment_id)
        if not ap:
            return {"error": f"Appointment '{appointment_id}' not found."}
        if ap["status"] != "booked":
            return {"error": f"Appointment '{appointment_id}' is already {ap['status']}."}

        ap["status"] = "cancelled"
        return {
            "appointment_id": appointment_id,
            "patient_id": ap["patient_id"],
            "doctor_id": ap["doctor_id"],
            "date": ap["date"],
            "start": ap["start"],
            "status": "cancelled",
        }

    # ------------------------------------------------------------------
    # Tool: lookup_patient
    # ------------------------------------------------------------------

    def lookup_patient(
        self,
        name: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        """
        Resolve a caller to patient records.

        Returns candidates list — never picks one when multiple match.
        Matching is fuzzy on name (case-insensitive substring) and exact on phone.
        """
        if not name and not phone:
            return {"error": "At least one of 'name' or 'phone' is required"}

        candidates = list(self._patients.values())

        if phone:
            phone_clean = phone.replace(" ", "").replace("-", "")
            candidates = [
                p for p in candidates
                if p["phone"].replace(" ", "") == phone_clean
            ]

        if name:
            name_lower = name.lower().strip()
            # Try exact match first, fall back to substring
            exact = [p for p in candidates if p["name"].lower() == name_lower]
            if exact:
                candidates = exact
            else:
                # token-based: all name tokens appear somewhere in patient name
                tokens = name_lower.split()
                candidates = [
                    p for p in candidates
                    if all(t in p["name"].lower() for t in tokens)
                ]

        if not candidates:
            return {"candidates": [], "count": 0}

        return {
            "candidates": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "phone": p["phone"],
                    "dob": p["dob"],
                    "guardian_of": p.get("guardian_of", []),
                }
                for p in candidates
            ],
            "count": len(candidates),
        }

    # ------------------------------------------------------------------
    # Tool: escalate_to_human
    # ------------------------------------------------------------------

    def escalate_to_human(self, reason: str, detail: str = "") -> dict[str, Any]:
        """
        Signal that this conversation must be handled by a human.

        reason : one of clinical_urgent | medical_advice | not_authorised
                 | ambiguous_patient | out_of_scope
        detail : free-text note for the human agent
        """
        valid_reasons = {
            "clinical_urgent", "medical_advice", "not_authorised",
            "ambiguous_patient", "out_of_scope",
        }
        if reason not in valid_reasons:
            return {
                "error": f"Invalid reason '{reason}'. "
                         f"Must be one of: {', '.join(sorted(valid_reasons))}"
            }
        return {"escalated": True, "reason": reason, "detail": detail}

    # ------------------------------------------------------------------
    # Read helpers used by the agent layer
    # ------------------------------------------------------------------

    def get_appointments_for_patient(
        self, patient_id: str, date_str: str | None = None
    ) -> list[dict]:
        aps = [
            a for a in self._appointments.values()
            if a["patient_id"] == patient_id and a["status"] == "booked"
        ]
        if date_str:
            aps = [a for a in aps if a["date"] == date_str]
        return sorted(aps, key=lambda a: (a["date"], a["start"]))

    def get_appointment(self, appointment_id: str) -> dict | None:
        return self._appointments.get(appointment_id)

    def get_doctor_name(self, doctor_id: str) -> str:
        d = self._doctors.get(doctor_id)
        return d["name"] if d else doctor_id

    def get_patient_name(self, patient_id: str) -> str:
        p = self._patients.get(patient_id)
        return p["name"] if p else patient_id
