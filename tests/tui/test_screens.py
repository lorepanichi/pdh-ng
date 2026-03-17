from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from textual.app import App, ComposeResult

from pdh_ng.tui.screens import IncidentsScreen, _cell_value, _colored, _fmt_age, _urgency_marker
from pdh_ng.tui.widgets import DEFAULT_COLUMNS, StatusBar


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


class _IncidentsApp(App):
    def __init__(self, prefs: dict | None = None) -> None:
        super().__init__()
        self.cfg = {"apikey": "x", "uid": "U1", "email": "a@b.com"}
        self._prefs = prefs or {}
        self.visible_columns = DEFAULT_COLUMNS[:]
        self.refresh_interval = 5
        self._prefs_saved: dict | None = None

    @property
    def scope(self) -> str:
        return self._prefs.get("scope", "mine")

    @property
    def status_mode(self) -> str:
        return self._prefs.get("status_mode", "all")

    def save_prefs(self) -> None:
        self._prefs_saved = dict(self._prefs)

    def compose(self) -> ComposeResult:
        yield IncidentsScreen()


class TestIncidentsScreenAutoRefresh:
    async def test_schedule_next_refresh_sets_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._schedule_next_refresh()
                assert screen._refresh_timer is not None

    async def test_schedule_next_refresh_interval_zero_no_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._refresh_interval = 0
                screen._schedule_next_refresh()
                assert screen._refresh_timer is None

    async def test_next_refresh_scheduled_after_populate(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._populate_table([], "mine", "")
                assert screen._refresh_timer is not None

    async def test_next_refresh_scheduled_after_error(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._set_error("timeout")
                assert screen._refresh_timer is not None

    async def test_start_refresh_zero_clears_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._start_refresh(5)
                assert screen._refresh_timer is not None
                screen._start_refresh(0)
                assert screen._refresh_timer is None

    async def test_start_refresh_positive_sets_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._start_refresh(0)
                assert screen._refresh_timer is None
                screen._start_refresh(3)
                assert screen._refresh_timer is not None

    async def test_cycling_to_off_stops_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                bar = pilot.app.query_one(StatusBar)
                while bar._refresh_interval != 0:
                    bar.cycle_refresh()
                await pilot.pause()
                assert screen._refresh_timer is None

    async def test_cycling_from_off_restarts_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                bar = pilot.app.query_one(StatusBar)
                while bar._refresh_interval != 0:
                    bar.cycle_refresh()
                await pilot.pause()
                bar.cycle_refresh()  # off -> 3s
                await pilot.pause()
                assert screen._refresh_timer is not None


class TestIncidentsScreenStatePrefs:
    async def test_scope_loaded_from_prefs(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp(prefs={"scope": "team"}).run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                assert screen._scope == "team"

    async def test_status_mode_loaded_from_prefs(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp(prefs={"status_mode": "triggered"}).run_test() as pilot:
                bar = pilot.app.query_one(StatusBar)
                assert bar._status_mode == "triggered"

    async def test_on_unmount_saves_scope(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            app = _IncidentsApp()
            async with app.run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._scope = "all"
                screen.on_unmount()
            assert app._prefs.get("scope") == "all"
            assert app._prefs_saved is not None

    async def test_on_unmount_saves_status_mode(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            app = _IncidentsApp()
            async with app.run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._status_mode = "acknowledged"
                screen.on_unmount()
            assert app._prefs.get("status_mode") == "acknowledged"
            assert app._prefs_saved is not None
