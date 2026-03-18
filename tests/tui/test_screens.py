from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Input

from pdh_ng.tui.screens import (
    IncidentDetailScreen,
    IncidentsScreen,
    _apply_title_filter,
    _cell_value,
    _colored,
    _fmt_age,
    _urgency_marker,
)
from pdh_ng.tui.constants import ALL_COLUMNS, IncScope, IncStatus, IncUrgency, RefreshTime
from pdh_ng.tui.widgets import ConfirmDialog, SnoozeDialog, StatusBar


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
        assert result == " "

    def test_unknown_urgency(self):
        result = _urgency_marker({"urgency": "unknown"})
        assert result == " "


class TestApplyTitleFilter:
    _incs = [
        {"title": "CPU spike on web-01"},
        {"title": "Memory leak in worker"},
        {"title": "Disk full on db-02"},
    ]

    def test_empty_filter_returns_all(self):
        assert _apply_title_filter(self._incs, "") == self._incs

    def test_positive_filter_matches_substring(self):
        result = _apply_title_filter(self._incs, "cpu")
        assert len(result) == 1
        assert result[0]["title"] == "CPU spike on web-01"

    def test_positive_filter_case_insensitive(self):
        result = _apply_title_filter(self._incs, "CPU")
        assert len(result) == 1

    def test_positive_filter_no_match(self):
        assert _apply_title_filter(self._incs, "network") == []

    def test_negative_filter_excludes_match(self):
        result = _apply_title_filter(self._incs, "!cpu")
        titles = [i["title"] for i in result]
        assert "CPU spike on web-01" not in titles
        assert len(result) == 2

    def test_negative_filter_case_insensitive(self):
        result = _apply_title_filter(self._incs, "!CPU")
        assert len(result) == 2

    def test_negative_filter_no_match_returns_all(self):
        result = _apply_title_filter(self._incs, "!network")
        assert result == self._incs

    def test_bang_only_excludes_all(self):
        result = _apply_title_filter(self._incs, "!")
        assert result == []


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
    CSS = "#title-filter { display: none; }"

    def __init__(self, prefs: dict | None = None) -> None:
        super().__init__()
        self.cfg = {"apikey": "x", "uid": "U1", "email": "a@b.com"}
        self._prefs = prefs or {}
        self.visible_columns = ALL_COLUMNS[:]
        self.refresh_time = RefreshTime.S5
        self._prefs_saved: dict | None = None

    @property
    def inc_scope(self) -> IncScope:
        return IncScope(self._prefs.get("inc_scope", IncScope.MINE))

    @inc_scope.setter
    def inc_scope(self, value: IncScope) -> None:
        self._prefs["inc_scope"] = int(value)

    @property
    def inc_status(self) -> IncStatus:
        return IncStatus(self._prefs.get("inc_status", IncStatus.ALL))

    @inc_status.setter
    def inc_status(self, value: IncStatus) -> None:
        self._prefs["inc_status"] = int(value)

    @property
    def inc_urgency(self) -> IncUrgency:
        return IncUrgency(self._prefs.get("inc_urgency", IncUrgency.ALL))

    @inc_urgency.setter
    def inc_urgency(self, value: IncUrgency) -> None:
        self._prefs["inc_urgency"] = int(value)

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
                screen._refresh_time = RefreshTime.OFF
                screen._schedule_next_refresh()
                assert screen._refresh_timer is None

    async def test_next_refresh_scheduled_after_populate(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._populate_table([], IncScope.MINE, "")
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
                screen._start_refresh(RefreshTime.S5)
                assert screen._refresh_timer is not None
                screen._start_refresh(RefreshTime.OFF)
                assert screen._refresh_timer is None

    async def test_start_refresh_positive_sets_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._start_refresh(RefreshTime.OFF)
                assert screen._refresh_timer is None
                screen._start_refresh(RefreshTime.S3)
                assert screen._refresh_timer is not None

    async def test_cycling_to_off_stops_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                bar = pilot.app.query_one(StatusBar)
                while bar._refresh_time != RefreshTime.OFF:
                    bar.cycle_refresh()
                await pilot.pause()
                assert screen._refresh_timer is None

    async def test_cycling_from_off_restarts_timer(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                bar = pilot.app.query_one(StatusBar)
                while bar._refresh_time != RefreshTime.OFF:
                    bar.cycle_refresh()
                await pilot.pause()
                bar.cycle_refresh()  # off -> S3
                await pilot.pause()
                assert screen._refresh_timer is not None


class TestIncidentsScreenStatePrefs:
    async def test_scope_loaded_from_prefs(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp(prefs={"inc_scope": int(IncScope.TEAM)}).run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                assert screen._inc_scope == IncScope.TEAM

    async def test_status_loaded_from_prefs(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            prefs = {"inc_status": int(IncStatus.TRIGGERED)}
            async with _IncidentsApp(prefs=prefs).run_test() as pilot:
                bar = pilot.app.query_one(StatusBar)
                assert bar._inc_status == IncStatus.TRIGGERED

    async def test_on_unmount_calls_save_prefs(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            app = _IncidentsApp()
            async with app.run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen.on_unmount()
            assert app._prefs_saved is not None

    async def test_scope_changed_persists(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._on_scope_changed(StatusBar.ScopeChanged(inc_scope=IncScope.ALL))
                assert pilot.app._prefs.get("inc_scope") == int(IncScope.ALL)

    async def test_status_changed_persists(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._on_status_changed(StatusBar.StatusChanged(inc_status=IncStatus.TRIGGERED))
                assert pilot.app._prefs.get("inc_status") == int(IncStatus.TRIGGERED)

    async def test_urgency_changed_persists(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._on_urgency_changed(StatusBar.UrgencyChanged(inc_urgency=IncUrgency.HIGH))
                assert pilot.app._prefs.get("inc_urgency") == int(IncUrgency.HIGH)

    async def test_apply_column_selection_uses_scope(self):
        """Regression: _apply_column_selection must pass _inc_scope, not the removed _mine_only."""
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp(prefs={"inc_scope": int(IncScope.ALL)}).run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._incidents_cache = {}
                screen._apply_column_selection(["title", "status"])
                assert screen._visible_columns == ["title", "status"]

    async def test_apply_column_selection_none_is_noop(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                original = screen._visible_columns[:]
                screen._apply_column_selection(None)
                assert screen._visible_columns == original


class TestIncidentsScreenFilter:
    async def test_enter_sets_filter_and_hides_input(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen.action_toggle_filter()
                await pilot.pause()
                filter_input = pilot.app.query_one("#title-filter", Input)
                filter_input.value = "cpu spike"
                await pilot.pause()

                screen._on_title_filter_submitted(Input.Submitted(filter_input, "cpu spike"))
                await pilot.pause()

                assert not filter_input.display
                assert screen._title_filter == "cpu spike"

    async def test_enter_triggers_load(self):
        with patch.object(IncidentsScreen, "load_incidents") as mock_load:
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen.action_toggle_filter()
                await pilot.pause()
                filter_input = pilot.app.query_one("#title-filter", Input)
                mock_load.reset_mock()

                screen._on_title_filter_submitted(Input.Submitted(filter_input, "test"))
                await pilot.pause()

                mock_load.assert_called_once()

    async def test_escape_hides_without_clearing_filter(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._title_filter = "cpu spike"
                screen.action_toggle_filter()
                await pilot.pause()
                filter_input = pilot.app.query_one("#title-filter")

                screen.action_clear_or_hide_filter()
                await pilot.pause()

                assert not filter_input.display
                assert screen._title_filter == "cpu spike"

    async def test_escape_does_not_trigger_load(self):
        with patch.object(IncidentsScreen, "load_incidents") as mock_load:
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen.action_toggle_filter()
                await pilot.pause()
                mock_load.reset_mock()

                screen.action_clear_or_hide_filter()
                await pilot.pause()

                mock_load.assert_not_called()

    async def test_toggle_open_prepopulates_current_filter(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._title_filter = "cpu spike"

                screen.action_toggle_filter()
                await pilot.pause()

                filter_input = pilot.app.query_one("#title-filter", Input)
                assert filter_input.display
                assert filter_input.value == "cpu spike"

    async def test_toggle_hide_preserves_filter_value(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._title_filter = "cpu spike"
                screen.action_toggle_filter()
                await pilot.pause()

                screen.action_toggle_filter()
                await pilot.pause()

                assert not pilot.app.query_one("#title-filter").display
                assert screen._title_filter == "cpu spike"

    async def test_filter_persists_through_refresh(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._title_filter = "cpu spike"

                screen._on_refresh_timer()
                await pilot.pause()

                assert screen._title_filter == "cpu spike"


_SAMPLE_INC = {
    "id": "I1",
    "title": "Test incident",
    "status": "triggered",
    "urgency": "high",
    "assignments": [],
    "service": {"summary": "web"},
    "created_at": "2024-01-01T00:00:00Z",
    "html_url": "https://example.pagerduty.com/incidents/I1",
}


class TestIncidentsScreenViewDetail:
    async def test_pushes_detail_screen_for_cursor_row(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._incident_ids = ["I1"]
                screen._incidents_cache = {"I1": _SAMPLE_INC}
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_view_detail()
                    await pilot.pause()
                    mock_push.assert_called_once()
                    assert isinstance(mock_push.call_args[0][0], IncidentDetailScreen)

    async def test_does_nothing_when_table_empty(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._incident_ids = []
                screen._incidents_cache = {}
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_view_detail()
                    await pilot.pause()
                    mock_push.assert_not_called()

    async def test_does_nothing_when_incident_missing_from_cache(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._incident_ids = ["I1"]
                screen._incidents_cache = {}
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_view_detail()
                    await pilot.pause()
                    mock_push.assert_not_called()


class TestIncidentsScreenToggleSelect:
    async def test_selects_incident_at_cursor(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._populate_table([_SAMPLE_INC], IncScope.MINE, "")
                await pilot.pause()

                screen.action_toggle_select()
                await pilot.pause()

                assert "I1" in screen._selected_ids

    async def test_deselects_already_selected_incident(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._populate_table([_SAMPLE_INC], IncScope.MINE, "")
                await pilot.pause()
                screen._selected_ids.add("I1")

                screen.action_toggle_select()
                await pilot.pause()

                assert "I1" not in screen._selected_ids

    async def test_does_nothing_when_table_empty(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen.action_toggle_select()
                await pilot.pause()
                assert not screen._selected_ids

    async def test_escape_clears_all_selections(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._populate_table([_SAMPLE_INC], IncScope.MINE, "")
                await pilot.pause()
                screen._selected_ids.add("I1")

                screen.action_clear_or_hide_filter()
                await pilot.pause()

                assert not screen._selected_ids


class TestIncidentsScreenBulkActions:
    async def test_ack_pushes_confirm_dialog_for_cursor_incident(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._incident_ids = ["I1"]
                screen._incidents_cache = {"I1": _SAMPLE_INC}
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_ack_selected()
                    await pilot.pause()
                    mock_push.assert_called_once()
                    dialog = mock_push.call_args[0][0]
                    assert isinstance(dialog, ConfirmDialog)
                    assert "1" in dialog._message

    async def test_ack_pushes_confirm_dialog_for_selected_incidents(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                inc2 = {**_SAMPLE_INC, "id": "I2"}
                screen._incident_ids = ["I1", "I2"]
                screen._incidents_cache = {"I1": _SAMPLE_INC, "I2": inc2}
                screen._selected_ids = {"I1", "I2"}
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_ack_selected()
                    await pilot.pause()
                    mock_push.assert_called_once()
                    dialog = mock_push.call_args[0][0]
                    assert isinstance(dialog, ConfirmDialog)
                    assert "2" in dialog._message

    async def test_ack_does_nothing_when_no_incidents(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_ack_selected()
                    await pilot.pause()
                    mock_push.assert_not_called()

    async def test_resolve_pushes_confirm_dialog(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._incident_ids = ["I1"]
                screen._incidents_cache = {"I1": _SAMPLE_INC}
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_resolve_selected()
                    await pilot.pause()
                    mock_push.assert_called_once()
                    dialog = mock_push.call_args[0][0]
                    assert isinstance(dialog, ConfirmDialog)
                    assert "Resolve" in dialog._message

    async def test_resolve_does_nothing_when_no_incidents(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_resolve_selected()
                    await pilot.pause()
                    mock_push.assert_not_called()

    async def test_snooze_pushes_snooze_dialog(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                screen._incident_ids = ["I1"]
                screen._incidents_cache = {"I1": _SAMPLE_INC}
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_snooze_selected()
                    await pilot.pause()
                    mock_push.assert_called_once()
                    assert isinstance(mock_push.call_args[0][0], SnoozeDialog)

    async def test_snooze_does_nothing_when_no_incidents(self):
        with patch.object(IncidentsScreen, "load_incidents"):
            async with _IncidentsApp().run_test() as pilot:
                screen = pilot.app.query_one(IncidentsScreen)
                with patch.object(pilot.app, "push_screen") as mock_push:
                    screen.action_snooze_selected()
                    await pilot.pause()
                    mock_push.assert_not_called()
