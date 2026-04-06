"""Tests for Nestldown roster event parsing."""
from nestldown_roster import parse_event_summary, is_booking_event


class TestParseEventSummary:
    """Test parsing calendar event summaries into roster data."""

    def test_assigned_dj(self):
        result = parse_event_summary("[HK] Smith/Jones")
        assert result["couple"] == "Smith/Jones"
        assert result["dj_name"] == "Henry Kim"
        assert result["email"] == "henry@bigfundj.com"
        assert result["phone"] == "1-800-924-4386 ext. 702"

    def test_assigned_dj_with_planner(self):
        result = parse_event_summary("[SB] Garcia/Chen (planner)")
        assert result["couple"] == "Garcia/Chen"
        assert result["dj_name"] == "Stefano Bortolin"
        assert "(planner)" not in result["couple"]

    def test_unassigned_event_up(self):
        result = parse_event_summary("[UP] Williams/Park")
        assert result["couple"] == "Williams/Park"
        assert result["dj_name"] == "Unassigned"
        assert result["email"] == "info@bigfundj.com"
        assert result["phone"] == "1-800-924-4386"

    def test_unassigned_event_uh(self):
        result = parse_event_summary("[UH] Taylor/Lee")
        assert result["dj_name"] == "Unassigned"
        assert result["email"] == "info@bigfundj.com"

    def test_unknown_initials_treated_as_unassigned(self):
        result = parse_event_summary("[ZZ] Mystery/Couple")
        assert result["dj_name"] == "Unassigned"


class TestIsBookingEvent:
    """Test filtering out non-booking calendar events."""

    def test_normal_booking(self):
        assert is_booking_event("[HK] Smith/Jones") is True

    def test_backup_dj_excluded(self):
        assert is_booking_event("[HK] BACKUP DJ") is False

    def test_paid_backup_dj_excluded(self):
        assert is_booking_event("[SB] PAID BACKUP DJ") is False

    def test_hold_excluded(self):
        assert is_booking_event("[PB] Hold to DJ Smith/Jones") is False

    def test_dad_duty_excluded(self):
        assert is_booking_event("[PB] DAD-DUTY") is False

    def test_case_insensitive_exclusion(self):
        assert is_booking_event("[HK] backup dj") is False


class TestParseEdgeCases:
    """Test edge cases in summary parsing."""

    def test_malformed_summary_no_brackets(self):
        assert parse_event_summary("Smith/Jones no brackets") is None

    def test_empty_summary(self):
        assert parse_event_summary("") is None
