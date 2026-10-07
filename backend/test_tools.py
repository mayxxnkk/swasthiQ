"""
test_tools.py — Unit tests for the tool layer (clinic_store.py).

These tests exercise the ClinicStore directly with no LLM involvement.
Run with:  python -m pytest test_tools.py -v
"""
import copy
import json
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Load clinic data once
# ---------------------------------------------------------------------------

CLINIC_PATH = (
    pathlib.Path(__file__).parent.parent
    / "swasthiq-front-desk-agent-starter-pack"
    / "clinic.json"
)
if not CLINIC_PATH.exists():
    # fallback
    import pathlib as _p
    CLINIC_PATH = _p.Path.home() / "Downloads" / "swasthiq-front-desk-agent-starter-pack" / "clinic.json"

with open(CLINIC_PATH, encoding="utf-8") as _fh:
    CLINIC_DATA = json.load(_fh)


def make_store():
    from clinic_store import ClinicStore
    return ClinicStore.from_json(CLINIC_DATA)


# ===========================================================================
# search_slots
# ===========================================================================

class TestSearchSlots:
    def test_returns_free_slots_on_working_day(self):
        store = make_store()
        result = store.search_slots("dr_rao", "2026-10-03")
        assert "slots" in result
        assert len(result["slots"]) > 0, "Expected free slots on Sat 2026-10-03"

    def test_no_slots_on_holiday(self):
        store = make_store()
        result = store.search_slots("dr_rao", "2026-10-02")
        assert result.get("slots") == []
        assert result.get("reason") == "clinic_closed"

    def test_no_slots_on_sunday(self):
        store = make_store()
        result = store.search_slots("dr_rao", "2026-10-04")
        assert result.get("slots") == []

    def test_no_slots_when_doctor_on_leave(self):
        store = make_store()
        result = store.search_slots("dr_rao", "2026-10-09")
        assert result.get("slots") == []
        assert result.get("reason") == "doctor_on_leave"

    def test_morning_window_filter(self):
        store = make_store()
        result = store.search_slots("dr_rao", "2026-10-08", window="morning")
        assert "slots" in result
        for slot in result["slots"]:
            h, m = map(int, slot.split(":"))
            assert h < 12, f"Slot {slot} is not morning"

    def test_evening_window_filter(self):
        store = make_store()
        result = store.search_slots("dr_rao", "2026-10-08", window="evening")
        assert "slots" in result
        for slot in result["slots"]:
            h, _ = map(int, slot.split(":"))
            assert h >= 16, f"Slot {slot} is not evening"

    def test_unknown_doctor(self):
        store = make_store()
        result = store.search_slots("dr_unknown", "2026-10-03")
        assert "error" in result

    def test_invalid_date_format(self):
        store = make_store()
        result = store.search_slots("dr_rao", "01/10/2026")
        assert "error" in result

    def test_booked_slot_not_in_free_list(self):
        """ap_0006: pt_0016 has dr_rao on 2026-10-03 at 09:15"""
        store = make_store()
        result = store.search_slots("dr_rao", "2026-10-03")
        assert "09:15" not in result["slots"], "09:15 is already booked"


# ===========================================================================
# book_appointment
# ===========================================================================

class TestBookAppointment:
    def test_happy_path(self):
        store = make_store()
        result = store.book_appointment("pt_0013", "dr_rao", "2026-10-08", "11:00")
        assert "appointment_id" in result
        assert result["status"] == "booked"

    def test_double_booking_rejected(self):
        """Book a slot, then try to book the same slot again."""
        store = make_store()
        result1 = store.book_appointment("pt_0013", "dr_rao", "2026-10-08", "11:00")
        assert "appointment_id" in result1
        result2 = store.book_appointment("pt_0015", "dr_rao", "2026-10-08", "11:00")
        assert "error" in result2, "Double-booking must be rejected"

    def test_rejects_already_booked_slot(self):
        """ap_0015: dr_rao 2026-10-08 09:00 is taken"""
        store = make_store()
        result = store.book_appointment("pt_0013", "dr_rao", "2026-10-08", "09:00")
        assert "error" in result

    def test_rejects_unknown_patient(self):
        store = make_store()
        result = store.book_appointment("pt_9999", "dr_rao", "2026-10-08", "11:00")
        assert "error" in result

    def test_rejects_unknown_doctor(self):
        store = make_store()
        result = store.book_appointment("pt_0013", "dr_unknown", "2026-10-08", "11:00")
        assert "error" in result

    def test_rejects_missing_fields(self):
        store = make_store()
        result = store.book_appointment("", "dr_rao", "2026-10-08", "11:00")
        assert "error" in result

    def test_rejects_slot_outside_window(self):
        """dr_rao has no slot at 14:00 on a Saturday"""
        store = make_store()
        result = store.book_appointment("pt_0013", "dr_rao", "2026-10-03", "14:00")
        assert "error" in result

    def test_appointment_id_is_unique(self):
        store = make_store()
        r1 = store.book_appointment("pt_0013", "dr_rao", "2026-10-08", "11:00")
        r2 = store.book_appointment("pt_0015", "dr_rao", "2026-10-08", "11:15")
        assert r1["appointment_id"] != r2["appointment_id"]


# ===========================================================================
# reschedule_appointment
# ===========================================================================

class TestRescheduleAppointment:
    def test_happy_path(self):
        """Reschedule ap_0001 (pt_0001 dr_rao 2026-10-01 09:30) to Sat 09:00"""
        store = make_store()
        result = store.reschedule_appointment("ap_0001", "2026-10-03", "09:00")
        assert "appointment_id" in result
        assert result["new_date"] == "2026-10-03"
        assert result["new_start"] == "09:00"
        assert result["status"] == "booked"

    def test_old_slot_freed_after_reschedule(self):
        """After reschedule, the old slot should be free again"""
        store = make_store()
        store.reschedule_appointment("ap_0001", "2026-10-03", "09:00")
        free = store.search_slots("dr_rao", "2026-10-01")
        assert "09:30" in free["slots"], "Old slot should be free now"

    def test_rejects_nonexistent_appointment(self):
        store = make_store()
        result = store.reschedule_appointment("ap_9999", "2026-10-03", "09:00")
        assert "error" in result

    def test_rejects_target_already_booked(self):
        """ap_0006 is already at dr_rao 2026-10-03 09:15; try to move ap_0001 there"""
        store = make_store()
        result = store.reschedule_appointment("ap_0001", "2026-10-03", "09:15")
        assert "error" in result

    def test_rejects_doctor_on_leave(self):
        store = make_store()
        result = store.reschedule_appointment("ap_0001", "2026-10-09", "09:00")
        assert "error" in result


# ===========================================================================
# cancel_appointment
# ===========================================================================

class TestCancelAppointment:
    def test_happy_path(self):
        store = make_store()
        result = store.cancel_appointment("ap_0001")
        assert result["status"] == "cancelled"

    def test_slot_freed_after_cancel(self):
        store = make_store()
        store.cancel_appointment("ap_0001")
        free = store.search_slots("dr_rao", "2026-10-01")
        assert "09:30" in free["slots"]

    def test_rejects_nonexistent_appointment(self):
        store = make_store()
        result = store.cancel_appointment("ap_9999")
        assert "error" in result

    def test_rejects_double_cancel(self):
        store = make_store()
        store.cancel_appointment("ap_0001")
        result = store.cancel_appointment("ap_0001")
        assert "error" in result

    def test_rejects_missing_id(self):
        store = make_store()
        result = store.cancel_appointment("")
        assert "error" in result


# ===========================================================================
# lookup_patient
# ===========================================================================

class TestLookupPatient:
    def test_exact_name_match(self):
        store = make_store()
        result = store.lookup_patient(name="Harpreet Kaur")
        assert result["count"] == 1
        assert result["candidates"][0]["id"] == "pt_0014"

    def test_ambiguous_name_returns_all_candidates(self):
        """Sharma must return all three Sharmas"""
        store = make_store()
        result = store.lookup_patient(name="Sharma")
        assert result["count"] >= 3, f"Expected ≥3 Sharma patients, got {result['count']}"

    def test_phone_disambiguates(self):
        """Priya Nair has phone 9812200104, Priya Menon has 9812200135"""
        store = make_store()
        result = store.lookup_patient(name="Priya", phone="9812200104")
        assert result["count"] == 1
        assert result["candidates"][0]["id"] == "pt_0004"

    def test_phone_only(self):
        store = make_store()
        result = store.lookup_patient(phone="9812200311")
        assert result["count"] == 1
        assert result["candidates"][0]["id"] == "pt_0013"

    def test_no_results(self):
        store = make_store()
        result = store.lookup_patient(name="Nonexistent Person")
        assert result["count"] == 0

    def test_rejects_empty_query(self):
        store = make_store()
        result = store.lookup_patient()
        assert "error" in result

    def test_guardian_lookup(self):
        """Sunita Gupta is guardian_of pt_0006 and pt_0007"""
        store = make_store()
        result = store.lookup_patient(name="Sunita Gupta")
        assert result["count"] == 1
        candidate = result["candidates"][0]
        assert "pt_0006" in candidate["guardian_of"]
        assert "pt_0007" in candidate["guardian_of"]


# ===========================================================================
# escalate_to_human
# ===========================================================================

class TestEscalateToHuman:
    def test_valid_reason(self):
        store = make_store()
        for reason in [
            "clinical_urgent", "medical_advice", "not_authorised",
            "ambiguous_patient", "out_of_scope",
        ]:
            result = store.escalate_to_human(reason=reason)
            assert result.get("escalated") is True
            assert result["reason"] == reason

    def test_invalid_reason(self):
        store = make_store()
        result = store.escalate_to_human(reason="unknown_reason")
        assert "error" in result

    def test_detail_is_optional(self):
        store = make_store()
        result = store.escalate_to_human(reason="out_of_scope")
        assert result.get("escalated") is True


# ===========================================================================
# Non-happy-path: concurrent booking race condition (simulated)
# ===========================================================================

class TestRaceCondition:
    def test_same_store_double_book_fails(self):
        """
        Simulates two 'concurrent' callers on the same ClinicStore instance
        trying to book the same slot.  The second must fail.
        """
        store = make_store()
        r1 = store.book_appointment("pt_0013", "dr_rao", "2026-10-08", "11:00")
        r2 = store.book_appointment("pt_0015", "dr_rao", "2026-10-08", "11:00")
        assert "appointment_id" in r1, "First booking should succeed"
        assert "error" in r2, "Second booking of same slot must fail"

    def test_independent_stores_both_succeed_in_isolation(self):
        """
        Each /agent/run gets its own ClinicStore.  Two requests for the same
        slot in isolation both 'succeed' (state resets per run).
        """
        store1 = make_store()
        store2 = make_store()
        r1 = store1.book_appointment("pt_0013", "dr_rao", "2026-10-08", "11:00")
        r2 = store2.book_appointment("pt_0015", "dr_rao", "2026-10-08", "11:00")
        assert "appointment_id" in r1
        assert "appointment_id" in r2


# ===========================================================================
# Non-happy-path: helper method
# ===========================================================================

class TestGetAppointmentsForPatient:
    def test_returns_appointments(self):
        store = make_store()
        aps = store.get_appointments_for_patient("pt_0001")
        assert any(a["id"] == "ap_0001" for a in aps)

    def test_date_filter(self):
        store = make_store()
        aps = store.get_appointments_for_patient("pt_0001", date_str="2026-10-01")
        assert all(a["date"] == "2026-10-01" for a in aps)

    def test_empty_for_unknown_patient(self):
        store = make_store()
        aps = store.get_appointments_for_patient("pt_9999")
        assert aps == []
