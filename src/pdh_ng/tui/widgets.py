from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Label, SelectionList
from textual.widgets.selection_list import Selection

from .constants import (
    _INC_SCOPE_CYCLE,
    _INC_SCOPE_LABELS,
    _INC_STATUS_CYCLE,
    _INC_STATUS_LABELS,
    _INC_STATUS_VARIANTS,
    _INC_URGENCY_CYCLE,
    _INC_URGENCY_LABELS,
    _INC_URGENCY_VARIANTS,
    _REFRESH_TIME_CYCLE,
    _REFRESH_TIME_LABELS,
    ALL_COLUMNS,
    IncScope,
    IncStatus,
    IncUrgency,
    RefreshTime,
)


class StatusBar(Horizontal):
    class ScopeChanged(Message):
        def __init__(self, inc_scope: IncScope) -> None:
            super().__init__()
            self.inc_scope = inc_scope

    class StatusChanged(Message):
        def __init__(self, inc_status: IncStatus) -> None:
            super().__init__()
            self.inc_status = inc_status

    class UrgencyChanged(Message):
        def __init__(self, inc_urgency: IncUrgency) -> None:
            super().__init__()
            self.inc_urgency = inc_urgency

    class RefreshTimeChanged(Message):
        def __init__(self, refresh_time: RefreshTime) -> None:
            super().__init__()
            self.refresh_time = refresh_time

    def __init__(
        self,
        inc_scope: IncScope = IncScope.MINE,
        refresh_time: RefreshTime = RefreshTime.S5,
        inc_status: IncStatus = IncStatus.ALL,
        inc_urgency: IncUrgency = IncUrgency.ALL,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._inc_scope: IncScope = inc_scope
        self._inc_status: IncStatus = inc_status
        self._inc_urgency: IncUrgency = inc_urgency
        self._refresh_time: RefreshTime = refresh_time
        self._count_text: str = ""

    def compose(self) -> ComposeResult:
        yield Button(_INC_SCOPE_LABELS[self._inc_scope], id="scope-btn", compact=True, flat=True)
        yield Button(
            _INC_STATUS_LABELS[self._inc_status],
            id="status-btn",
            variant=_INC_STATUS_VARIANTS[self._inc_status],
            compact=True,
            flat=True,
        )
        yield Button(
            _INC_URGENCY_LABELS[self._inc_urgency],
            id="urgency-btn",
            variant=_INC_URGENCY_VARIANTS[self._inc_urgency],
            compact=True,
            flat=True,
        )
        yield Button(
            _REFRESH_TIME_LABELS[self._refresh_time],
            id="refresh-btn",
            compact=True,
            flat=True,
        )
        yield Label("", id="count-label")

    def set_count(self, count: int, title_filter: str = "", scope: str = "") -> None:
        suffix = f"  filter: {title_filter!r}" if title_filter else ""
        self._count_text = f"{count} incident(s){suffix}"
        self.query_one("#count-label", Label).update(f"   {self._count_text}")

    def set_loading(self) -> None:
        base = f"{self._count_text}  " if self._count_text else ""
        self.query_one("#count-label", Label).update(f"   {base}↻")

    def set_error(self, message: str) -> None:
        self.query_one("#count-label", Label).update(f"   [bold red]{message}[/bold red]")

    def _sync_buttons(self) -> None:
        self.query_one("#scope-btn", Button).label = _INC_SCOPE_LABELS[self._inc_scope]
        btn = self.query_one("#status-btn", Button)
        btn.label = _INC_STATUS_LABELS[self._inc_status]
        btn.variant = _INC_STATUS_VARIANTS[self._inc_status]
        self.query_one("#refresh-btn", Button).label = _REFRESH_TIME_LABELS[self._refresh_time]
        urgency_btn = self.query_one("#urgency-btn", Button)
        urgency_btn.label = _INC_URGENCY_LABELS[self._inc_urgency]
        urgency_btn.variant = _INC_URGENCY_VARIANTS[self._inc_urgency]

    def cycle_scope(self) -> None:
        idx = _INC_SCOPE_CYCLE.index(self._inc_scope)
        self._inc_scope = _INC_SCOPE_CYCLE[(idx + 1) % len(_INC_SCOPE_CYCLE)]
        self._sync_buttons()
        self.post_message(self.ScopeChanged(self._inc_scope))

    def cycle_status(self) -> None:
        idx = _INC_STATUS_CYCLE.index(self._inc_status)
        self._inc_status = _INC_STATUS_CYCLE[(idx + 1) % len(_INC_STATUS_CYCLE)]
        self._sync_buttons()
        self.post_message(self.StatusChanged(self._inc_status))

    def cycle_urgency(self) -> None:
        idx = _INC_URGENCY_CYCLE.index(self._inc_urgency)
        self._inc_urgency = _INC_URGENCY_CYCLE[(idx + 1) % len(_INC_URGENCY_CYCLE)]
        self._sync_buttons()
        self.post_message(self.UrgencyChanged(self._inc_urgency))

    def cycle_refresh(self) -> None:
        idx = _REFRESH_TIME_CYCLE.index(self._refresh_time)
        self._refresh_time = _REFRESH_TIME_CYCLE[(idx + 1) % len(_REFRESH_TIME_CYCLE)]
        self._sync_buttons()
        self.post_message(self.RefreshTimeChanged(self._refresh_time))

    @on(Button.Pressed, "#scope-btn")
    def _on_scope_btn(self) -> None:
        self.cycle_scope()

    @on(Button.Pressed, "#status-btn")
    def _on_status_btn(self) -> None:
        self.cycle_status()

    @on(Button.Pressed, "#urgency-btn")
    def _on_urgency_btn(self) -> None:
        self.cycle_urgency()

    @on(Button.Pressed, "#refresh-btn")
    def _on_refresh_btn(self) -> None:
        self.cycle_refresh()


class ColumnSelectorScreen(ModalScreen):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Apply", priority=True),
    ]

    def __init__(self, visible_columns: list[str]) -> None:
        super().__init__()
        self._visible_columns = set(visible_columns)

    def compose(self) -> ComposeResult:
        with Vertical(id="field-selector-dialog"):
            yield Label("Select columns [dim] space = toggle  enter = apply  esc = cancel[/dim]")
            selections = [
                Selection(col, col, initial_state=col in self._visible_columns)
                for col in ALL_COLUMNS
            ]
            yield SelectionList(*selections, id="field-selector-list")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        selected_set = set(self.query_one("#field-selector-list", SelectionList).selected)
        selected = [col for col in ALL_COLUMNS if col in selected_set]
        self.dismiss(selected if selected else None)


class SnoozeDialog(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="snooze-dialog"):
            yield Label("Snooze duration:")
            with Horizontal(id="snooze-buttons"):
                yield Button("1 hour", id="snooze-1h")
                yield Button("4 hours", id="snooze-4h")
                yield Button("8 hours", id="snooze-8h")

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#snooze-1h")
    def _snooze_1h(self) -> None:
        self.dismiss(3600)

    @on(Button.Pressed, "#snooze-4h")
    def _snooze_4h(self) -> None:
        self.dismiss(14400)

    @on(Button.Pressed, "#snooze-8h")
    def _snooze_8h(self) -> None:
        self.dismiss(28800)


class ConfirmDialog(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", id="confirm-yes", variant="error")
                yield Button("No", id="confirm-no", variant="primary")

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-yes")
    def _confirmed(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def _cancelled(self) -> None:
        self.dismiss(False)
