from textual.app import App, ComposeResult
from textual.widgets import Label, SelectionList

from pdh_ng.tui.constants import (
    ALL_COLUMNS,
    IncScope,
    IncStatus,
    IncUrgency,
    RefreshTime,
    _INC_URGENCY_LABELS,
    _REFRESH_TIME_CYCLE,
    _REFRESH_TIME_LABELS,
)
from pdh_ng.tui.widgets import ColumnSelectorScreen, SnoozeDialog, StatusBar


class StatusBarApp(App):
    CSS = ""

    def __init__(self, inc_scope=IncScope.MINE):
        super().__init__()
        self._inc_scope = inc_scope
        self.received_scopes: list[IncScope] = []
        self.received_statuses: list[IncStatus] = []
        self.received_urgencies: list[IncUrgency] = []
        self.received_refresh_times: list[RefreshTime] = []

    def compose(self) -> ComposeResult:
        yield StatusBar(inc_scope=self._inc_scope, id="status-bar")

    def on_status_bar_scope_changed(self, event: StatusBar.ScopeChanged) -> None:
        self.received_scopes.append(event.inc_scope)

    def on_status_bar_status_changed(self, event: StatusBar.StatusChanged) -> None:
        self.received_statuses.append(event.inc_status)

    def on_status_bar_urgency_changed(self, event: StatusBar.UrgencyChanged) -> None:
        self.received_urgencies.append(event.inc_urgency)

    def on_status_bar_refresh_time_changed(self, event: StatusBar.RefreshTimeChanged) -> None:
        self.received_refresh_times.append(event.refresh_time)


class ModalApp(App):
    """Generic app that pushes a modal and captures the dismissed value."""

    CSS = ""

    def __init__(self, modal):
        super().__init__()
        self._modal = modal
        self.result = None

    def on_mount(self) -> None:
        self.push_screen(self._modal, self._capture)

    def _capture(self, value) -> None:
        self.result = value
        self.exit()


class TestStatusBar:
    async def test_initial_scope_mine(self):
        async with StatusBarApp(inc_scope=IncScope.MINE).run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_scope == IncScope.MINE

    async def test_cycle_scope(self):
        async with StatusBarApp(inc_scope=IncScope.MINE).run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_scope()
            assert bar._inc_scope == IncScope.TEAM
            bar.cycle_scope()
            assert bar._inc_scope == IncScope.ALL
            bar.cycle_scope()
            assert bar._inc_scope == IncScope.MINE

    async def test_cycle_status(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_status == IncStatus.ALL
            bar.cycle_status()
            assert bar._inc_status == IncStatus.TRIGGERED
            bar.cycle_status()
            assert bar._inc_status == IncStatus.ACK
            bar.cycle_status()
            assert bar._inc_status == IncStatus.ALL

    async def test_scope_button_cycles(self):
        async with StatusBarApp(inc_scope=IncScope.MINE).run_test() as pilot:
            await pilot.click("#inc-scope-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_scope == IncScope.TEAM

    async def test_status_button_cycles(self):
        async with StatusBarApp().run_test() as pilot:
            await pilot.click("#inc-status-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_status == IncStatus.TRIGGERED

    async def test_set_count(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_status(inc_count=5)
            label = bar.query_one("#status-label", Label)
            assert "5" in str(label.render())

    async def test_set_count_with_filter(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_status(inc_count=3, title_filter="disk")
            label = bar.query_one("#status-label", Label)
            assert "disk" in str(label.render())

    async def test_set_loading_no_prior_count(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_loading()
            label = bar.query_one("#status-label", Label)
            assert "↻" in str(label.render())

    async def test_set_loading_preserves_count(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_status(inc_count=7)
            bar.set_loading()
            label = bar.query_one("#status-label", Label)
            rendered = str(label.render())
            assert "7" in rendered
            assert "↻" in rendered

    async def test_set_error(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_error("something went wrong")
            label = bar.query_one("#status-label", Label)
            assert "something went wrong" in str(label.render())

    async def test_default_inc_status(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_status == IncStatus.ALL

    async def test_initial_inc_status_from_param(self):
        class _App(App):
            def compose(self) -> ComposeResult:
                yield StatusBar(inc_status=IncStatus.TRIGGERED, id="status-bar")

        async with _App().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_status == IncStatus.TRIGGERED

    async def test_default_refresh_time(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._refresh_time == RefreshTime.S5

    async def test_cycle_refresh_full_sequence(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_refresh()
            assert bar._refresh_time == RefreshTime.S10
            bar.cycle_refresh()
            assert bar._refresh_time == RefreshTime.OFF
            bar.cycle_refresh()
            assert bar._refresh_time == RefreshTime.S3
            bar.cycle_refresh()
            assert bar._refresh_time == RefreshTime.S5

    async def test_cycle_refresh_wraps(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            for _ in range(len(_REFRESH_TIME_CYCLE)):
                bar.cycle_refresh()
            assert bar._refresh_time == RefreshTime.S5

    async def test_refresh_button_label_updates(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            for expected in [RefreshTime.S10, RefreshTime.OFF, RefreshTime.S3, RefreshTime.S5]:
                bar.cycle_refresh()
                await pilot.pause()
                label = str(pilot.app.query_one("#refresh-time-btn").label)
                assert label == _REFRESH_TIME_LABELS[expected]

    async def test_refresh_button_click_cycles(self):
        async with StatusBarApp().run_test() as pilot:
            await pilot.click("#refresh-time-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._refresh_time == RefreshTime.S10

    async def test_scope_changed_message(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_scope()
            await pilot.pause()
            assert pilot.app.received_scopes == [IncScope.TEAM]

    async def test_status_changed_message(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_status()
            await pilot.pause()
            assert pilot.app.received_statuses == [IncStatus.TRIGGERED]

    async def test_urgency_changed_message(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_urgency()
            await pilot.pause()
            assert pilot.app.received_urgencies == [IncUrgency.HIGH]

    async def test_refresh_time_changed_message(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_refresh()
            await pilot.pause()
            assert pilot.app.received_refresh_times == [RefreshTime.S10]

    async def test_all_labels_have_refresh_symbol(self):
        for label in _REFRESH_TIME_LABELS.values():
            assert "↻" in label

    async def test_off_label(self):
        assert "off" in _REFRESH_TIME_LABELS[RefreshTime.OFF]

    async def test_default_inc_urgency(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_urgency == IncUrgency.ALL

    async def test_cycle_urgency(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_urgency()
            assert bar._inc_urgency == IncUrgency.HIGH
            bar.cycle_urgency()
            assert bar._inc_urgency == IncUrgency.LOW
            bar.cycle_urgency()
            assert bar._inc_urgency == IncUrgency.ALL

    async def test_urgency_button_cycles(self):
        async with StatusBarApp().run_test() as pilot:
            await pilot.click("#inc-urgency-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._inc_urgency == IncUrgency.HIGH

    async def test_urgency_button_label_updates(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            for expected in [IncUrgency.HIGH, IncUrgency.LOW, IncUrgency.ALL]:
                bar.cycle_urgency()
                await pilot.pause()
                label = str(pilot.app.query_one("#inc-urgency-btn").label)
                assert label == _INC_URGENCY_LABELS[expected]


class TestStatusBarAutoAck:
    async def test_default_auto_ack_is_off(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._auto_ack is False

    async def test_initial_auto_ack_from_param(self):
        class _App(App):
            def compose(self) -> ComposeResult:
                yield StatusBar(auto_ack=True, id="status-bar")

        async with _App().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._auto_ack is True

    async def test_toggle_auto_ack_turns_on(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.toggle_auto_ack()
            assert bar._auto_ack is True

    async def test_toggle_auto_ack_turns_off(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.toggle_auto_ack()
            bar.toggle_auto_ack()
            assert bar._auto_ack is False

    async def test_auto_ack_button_click_toggles(self):
        async with StatusBarApp().run_test() as pilot:
            await pilot.click("#auto-ack-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._auto_ack is True

    async def test_auto_ack_changed_message(self):
        class _App(App):
            CSS = ""

            def __init__(self):
                super().__init__()
                self.received: list[bool] = []

            def compose(self) -> ComposeResult:
                yield StatusBar(id="status-bar")

            def on_status_bar_auto_ack_changed(self, event: StatusBar.AutoAckChanged) -> None:
                self.received.append(event.auto_ack)

        async with _App().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.toggle_auto_ack()
            await pilot.pause()
            assert pilot.app.received == [True]
            bar.toggle_auto_ack()
            await pilot.pause()
            assert pilot.app.received == [True, False]

    async def test_auto_ack_button_label_on(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.toggle_auto_ack()
            await pilot.pause()
            label = str(pilot.app.query_one("#auto-ack-btn").label)
            assert "ON" in label

    async def test_auto_ack_button_label_off(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            await pilot.pause()
            label = str(pilot.app.query_one("#auto-ack-btn").label)
            assert "OFF" in label


class TestSnoozeDialog:
    async def test_1h_dismisses_3600(self):
        async with ModalApp(SnoozeDialog()).run_test() as pilot:
            await pilot.click("#snooze-1h")
            await pilot.pause()
        assert pilot.app.result == 3600

    async def test_4h_dismisses_14400(self):
        async with ModalApp(SnoozeDialog()).run_test() as pilot:
            await pilot.click("#snooze-4h")
            await pilot.pause()
        assert pilot.app.result == 14400

    async def test_8h_dismisses_28800(self):
        async with ModalApp(SnoozeDialog()).run_test() as pilot:
            await pilot.click("#snooze-8h")
            await pilot.pause()
        assert pilot.app.result == 28800

    async def test_escape_dismisses_none(self):
        async with ModalApp(SnoozeDialog()).run_test() as pilot:
            await pilot.press("escape")
            await pilot.pause()
        assert pilot.app.result is None


class TestColumnSelectorScreen:
    async def test_escape_dismisses_none(self):
        async with ModalApp(ColumnSelectorScreen(ALL_COLUMNS)).run_test() as pilot:
            await pilot.press("escape")
            await pilot.pause()
        assert pilot.app.result is None

    async def test_all_columns_shown(self):
        async with ModalApp(ColumnSelectorScreen(ALL_COLUMNS)).run_test() as pilot:
            await pilot.pause()
            selection_list = pilot.app.screen.query_one("#field-selector-list", SelectionList)
            assert len(list(selection_list._options)) == len(ALL_COLUMNS)

    async def test_confirm_returns_selected(self):
        async with ModalApp(ColumnSelectorScreen(["id", "title"])).run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause()
        assert pilot.app.result is not None
        assert "id" in pilot.app.result
        assert "title" in pilot.app.result

    async def test_confirm_preserves_all_columns_order(self):
        """Regression: re-enabling a column must not move it to the end."""
        async with ModalApp(ColumnSelectorScreen(ALL_COLUMNS)).run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause()
        assert pilot.app.result == ALL_COLUMNS

    async def test_confirm_subset_preserves_order(self):
        subset = ["title", "status", "age"]  # non-contiguous slice of ALL_COLUMNS
        async with ModalApp(ColumnSelectorScreen(subset)).run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause()
        result = pilot.app.result
        assert result is not None
        assert result == [c for c in ALL_COLUMNS if c in set(subset)]
