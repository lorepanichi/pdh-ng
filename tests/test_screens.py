from datetime import UTC, datetime, timedelta

from pdh_ng.tui.screens import _cell_value, _colored, _fmt_age, _urgency_marker


class TestFmtAge:
    def test_valid_utc_iso_string(self):
        dt = datetime.now(UTC) - timedelta(minutes=5)
        result = _fmt_age(dt.isoformat().replace("+00:00", "Z"))
        assert "minutes" in result or "ago" in result

    def test_valid_offset_iso_string(self):
        dt = datetime.now(UTC) - timedelta(hours=2)
        result = _fmt_age(dt.isoformat())
        assert "hours" in result or "ago" in result

    def test_invalid_string_returned_as_is(self):
        result = _fmt_age("not-a-date")
        assert result == "not-a-date"

    def test_empty_string_returned_as_is(self):
        result = _fmt_age("")
        assert result == ""


class TestColored:
    def test_wraps_in_markup(self):
        result = _colored("hello", "red")
        assert result == "[red]hello[/red]"

    def test_different_colors(self):
        assert _colored("x", "green") == "[green]x[/green]"
        assert _colored("x", "bold blue") == "[bold blue]x[/bold blue]"


class TestUrgencyMarker:
    def test_high_urgency(self):
        result = _urgency_marker({"urgency": "high"})
        assert "red" in result
        assert "▋" in result

    def test_low_urgency(self):
        result = _urgency_marker({"urgency": "low"})
        assert "blue" in result
        assert "▋" in result

    def test_missing_urgency(self):
        result = _urgency_marker({})
        assert result == ""

    def test_unknown_urgency(self):
        result = _urgency_marker({"urgency": "unknown"})
        assert result == ""


class TestCellValue:
    def test_id(self):
        assert _cell_value({"id": "I123"}, "id") == "I123"

    def test_id_missing(self):
        assert _cell_value({}, "id") == ""

    def test_title(self):
        assert _cell_value({"title": "Disk full"}, "title") == "Disk full"

    def test_status_triggered(self):
        result = _cell_value({"status": "triggered"}, "status")
        assert "triggered" in result
        assert "red" in result

    def test_status_acknowledged(self):
        result = _cell_value({"status": "acknowledged"}, "status")
        assert "acknowledged" in result
        assert "yellow" in result

    def test_status_resolved(self):
        result = _cell_value({"status": "resolved"}, "status")
        assert "resolved" in result
        assert "green" in result

    def test_status_unknown(self):
        result = _cell_value({"status": "unknown"}, "status")
        assert "unknown" in result
        assert "white" in result

    def test_assignee_single(self):
        inc = {"assignments": [{"assignee": {"summary": "Alice"}}]}
        assert _cell_value(inc, "assignee") == "Alice"

    def test_assignee_multiple(self):
        inc = {
            "assignments": [
                {"assignee": {"summary": "Alice"}},
                {"assignee": {"summary": "Bob"}},
            ]
        }
        assert _cell_value(inc, "assignee") == "Alice, Bob"

    def test_assignee_empty(self):
        assert _cell_value({"assignments": []}, "assignee") == ""

    def test_service(self):
        inc = {"service": {"summary": "payments"}}
        assert _cell_value(inc, "service") == "payments"

    def test_service_missing(self):
        assert _cell_value({}, "service") == ""

    def test_age(self):
        dt = datetime.now(UTC) - timedelta(minutes=10)
        inc = {"created_at": dt.isoformat().replace("+00:00", "Z")}
        result = _cell_value(inc, "age")
        assert result != ""

    def test_unknown_column(self):
        assert _cell_value({"foo": "bar"}, "nonexistent") == ""
