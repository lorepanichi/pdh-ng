from textual.app import App, ComposeResult
from textual.widgets import Label, SelectionList

from pdh_ng.pd import STATUS_ACK, STATUS_TRIGGERED
from pdh_ng.tui.widgets import (
    ALL_COLUMNS,
    ConfirmDialog,
    FieldSelectorScreen,
    SnoozeDialog,
    StatusBar,
    _REFRESH_CYCLE,
    _REFRESH_LABELS,
)


class StatusBarApp(App):
    CSS = ""

    def __init__(self, scope="mine"):
        super().__init__()
        self._scope = scope
        self.received_intervals: list[int] = []

    def compose(self) -> ComposeResult:
        yield StatusBar(scope=self._scope, id="status-bar")

    def on_status_bar_refresh_interval_changed(
        self, event: StatusBar.RefreshIntervalChanged
    ) -> None:
        self.received_intervals.append(event.interval)


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
        async with StatusBarApp(scope="mine").run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._scope == "mine"

    async def test_cycle_scope(self):
        async with StatusBarApp(scope="mine").run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_scope()
            assert bar._scope == "team"
            bar.cycle_scope()
            assert bar._scope == "all"
            bar.cycle_scope()
            assert bar._scope == "mine"

    async def test_cycle_status(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._status_mode == "all"
            bar.cycle_status()
            assert bar._status_mode == STATUS_TRIGGERED
            bar.cycle_status()
            assert bar._status_mode == STATUS_ACK
            bar.cycle_status()
            assert bar._status_mode == "all"

    async def test_active_statuses_all_mode(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar._status_mode = "all"
            assert set(bar._active_statuses()) == {STATUS_TRIGGERED, STATUS_ACK}

    async def test_active_statuses_triggered_mode(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar._status_mode = STATUS_TRIGGERED
            assert bar._active_statuses() == [STATUS_TRIGGERED]

    async def test_scope_button_cycles(self):
        async with StatusBarApp(scope="mine").run_test() as pilot:
            await pilot.click("#scope-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._scope == "team"

    async def test_status_button_cycles(self):
        async with StatusBarApp().run_test() as pilot:
            await pilot.click("#status-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._status_mode == STATUS_TRIGGERED

    async def test_set_count(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_count(5)
            label = bar.query_one("#count-label", Label)
            assert "5" in str(label.render())

    async def test_set_count_with_filter(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_count(3, title_filter="disk")
            label = bar.query_one("#count-label", Label)
            assert "disk" in str(label.render())

    async def test_set_loading_no_prior_count(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_loading()
            label = bar.query_one("#count-label", Label)
            assert "↻" in str(label.render())

    async def test_set_loading_preserves_count(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_count(7)
            bar.set_loading()
            label = bar.query_one("#count-label", Label)
            rendered = str(label.render())
            assert "7" in rendered
            assert "↻" in rendered

    async def test_set_error(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.set_error("something went wrong")
            label = bar.query_one("#count-label", Label)
            assert "something went wrong" in str(label.render())

    async def test_default_status_mode(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._status_mode == "all"

    async def test_initial_status_mode_from_param(self):
        app = StatusBarApp()
        async with app.run_test():
            pass

        class _App(App):
            def compose(self) -> ComposeResult:
                yield StatusBar(status_mode="triggered", id="status-bar")

        async with _App().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._status_mode == "triggered"

    async def test_default_refresh_interval(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._refresh_interval == 5

    async def test_cycle_refresh_full_sequence(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_refresh()
            assert bar._refresh_interval == 10
            bar.cycle_refresh()
            assert bar._refresh_interval == 0
            bar.cycle_refresh()
            assert bar._refresh_interval == 3
            bar.cycle_refresh()
            assert bar._refresh_interval == 5

    async def test_cycle_refresh_wraps(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            for _ in range(len(_REFRESH_CYCLE)):
                bar.cycle_refresh()
            assert bar._refresh_interval == 5

    async def test_refresh_button_label_updates(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            for expected in [10, 0, 3, 5]:
                bar.cycle_refresh()
                await pilot.pause()
                label = str(pilot.app.query_one("#refresh-btn").label)
                assert label == _REFRESH_LABELS[expected]

    async def test_refresh_button_click_cycles(self):
        async with StatusBarApp().run_test() as pilot:
            await pilot.click("#refresh-btn")
            bar = pilot.app.query_one("#status-bar", StatusBar)
            assert bar._refresh_interval == 10

    async def test_refresh_interval_changed_message(self):
        async with StatusBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#status-bar", StatusBar)
            bar.cycle_refresh()
            await pilot.pause()
            assert pilot.app.received_intervals == [10]

    async def test_all_labels_have_refresh_symbol(self):
        for label in _REFRESH_LABELS.values():
            assert "↻" in label

    async def test_off_label(self):
        assert "off" in _REFRESH_LABELS[0]


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


class TestConfirmDialog:
    async def test_yes_dismisses_true(self):
        async with ModalApp(ConfirmDialog("Are you sure?")).run_test() as pilot:
            await pilot.click("#confirm-yes")
            await pilot.pause()
        assert pilot.app.result is True

    async def test_no_dismisses_false(self):
        async with ModalApp(ConfirmDialog("Are you sure?")).run_test() as pilot:
            await pilot.click("#confirm-no")
            await pilot.pause()
        assert pilot.app.result is False

    async def test_escape_dismisses_false(self):
        async with ModalApp(ConfirmDialog("Are you sure?")).run_test() as pilot:
            await pilot.press("escape")
            await pilot.pause()
        assert pilot.app.result is False

    async def test_message_shown(self):
        async with ModalApp(ConfirmDialog("Delete incident?")).run_test() as pilot:
            await pilot.pause()
            label = pilot.app.screen.query_one("#confirm-dialog Label", Label)
            assert "Delete incident?" in str(label.render())


class TestFieldSelectorScreen:
    async def test_escape_dismisses_none(self):
        async with ModalApp(FieldSelectorScreen(ALL_COLUMNS)).run_test() as pilot:
            await pilot.press("escape")
            await pilot.pause()
        assert pilot.app.result is None

    async def test_all_columns_shown(self):
        async with ModalApp(FieldSelectorScreen(ALL_COLUMNS)).run_test() as pilot:
            await pilot.pause()
            selection_list = pilot.app.screen.query_one("#field-selector-list", SelectionList)
            assert len(list(selection_list._options)) == len(ALL_COLUMNS)

    async def test_confirm_returns_selected(self):
        async with ModalApp(FieldSelectorScreen(["id", "title"])).run_test() as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
        assert pilot.app.result is not None
        assert "id" in pilot.app.result
        assert "title" in pilot.app.result

    async def test_confirm_preserves_all_columns_order(self):
        """Regression: re-enabling a column must not move it to the end."""
        async with ModalApp(FieldSelectorScreen(ALL_COLUMNS)).run_test() as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
        assert pilot.app.result == ALL_COLUMNS

    async def test_confirm_subset_preserves_order(self):
        subset = ["title", "status", "age"]  # non-contiguous slice of ALL_COLUMNS
        async with ModalApp(FieldSelectorScreen(subset)).run_test() as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
        result = pilot.app.result
        assert result is not None
        assert result == [c for c in ALL_COLUMNS if c in set(subset)]
