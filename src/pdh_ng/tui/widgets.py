from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Label, SelectionList
from textual.widgets.selection_list import Selection

from ..pd import DEFAULT_URGENCIES, STATUS_ACK, STATUS_TRIGGERED

ALL_COLUMNS = ["id", "title", "status", "assignee", "service", "age"]
DEFAULT_COLUMNS = ["id", "title", "status", "assignee", "service", "age"]

_STATUS_CYCLE = ["all", STATUS_TRIGGERED, STATUS_ACK]
_STATUS_LABELS = {"all": "2:all statuses", STATUS_TRIGGERED: "2:triggered", STATUS_ACK: "2:ack'd"}
_STATUS_VARIANTS = {"all": "default", STATUS_TRIGGERED: "error", STATUS_ACK: "warning"}

_SCOPE_CYCLE = ["mine", "team", "all"]
_SCOPE_LABELS = {"mine": "1:mine", "team": "1:team", "all": "1:all"}

_REFRESH_CYCLE = [0, 3, 5, 10]
_REFRESH_LABELS = {0: "3:↻ off", 3: "3:↻  3s", 5: "3:↻  5s", 10: "3:↻ 10s"}


class StatusBar(Horizontal):
    class FiltersChanged(Message):
        def __init__(self, statuses: list[str], urgencies: list[str], scope: str, status_mode: str) -> None:
            super().__init__()
            self.statuses = statuses
            self.urgencies = urgencies
            self.scope = scope
            self.status_mode = status_mode

    class RefreshIntervalChanged(Message):
        def __init__(self, interval: int) -> None:
            super().__init__()
            self.interval = interval

    def __init__(self, scope: str = "mine", refresh_interval: int = 5, status_mode: str = "all", **kwargs) -> None:
        super().__init__(**kwargs)
        self._scope: str = scope
        self._status_mode: str = status_mode
        self._urgencies: set[str] = set(DEFAULT_URGENCIES)
        self._refresh_interval: int = refresh_interval
        self._count_text: str = ""

    def compose(self) -> ComposeResult:
        yield Button(_SCOPE_LABELS[self._scope], id="scope-btn", compact=True, flat=True)
        yield Button(
            _STATUS_LABELS[self._status_mode],
            id="status-btn",
            variant=_STATUS_VARIANTS[self._status_mode],
            compact=True,
            flat=True,
        )
        yield Button(
            _REFRESH_LABELS[self._refresh_interval],
            id="refresh-btn",
            compact=True,
            flat=True,
        )
        yield Label("", id="count-label")

    def _active_statuses(self) -> list[str]:
        if self._status_mode == "all":
            return [STATUS_TRIGGERED, STATUS_ACK]
        return [self._status_mode]

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
        self.query_one("#scope-btn", Button).label = _SCOPE_LABELS[self._scope]
        btn = self.query_one("#status-btn", Button)
        btn.label = _STATUS_LABELS[self._status_mode]
        btn.variant = _STATUS_VARIANTS[self._status_mode]
        self.query_one("#refresh-btn", Button).label = _REFRESH_LABELS[self._refresh_interval]

    def cycle_scope(self) -> None:
        idx = _SCOPE_CYCLE.index(self._scope)
        self._scope = _SCOPE_CYCLE[(idx + 1) % len(_SCOPE_CYCLE)]
        self._sync_buttons()
        self._emit()

    def cycle_status(self) -> None:
        idx = _STATUS_CYCLE.index(self._status_mode)
        self._status_mode = _STATUS_CYCLE[(idx + 1) % len(_STATUS_CYCLE)]
        self._sync_buttons()
        self._emit()

    def cycle_refresh(self) -> None:
        idx = _REFRESH_CYCLE.index(self._refresh_interval)
        self._refresh_interval = _REFRESH_CYCLE[(idx + 1) % len(_REFRESH_CYCLE)]
        self._sync_buttons()
        self.post_message(self.RefreshIntervalChanged(self._refresh_interval))

    @on(Button.Pressed, "#scope-btn")
    def _on_scope_btn(self) -> None:
        self.cycle_scope()

    @on(Button.Pressed, "#status-btn")
    def _on_status_btn(self) -> None:
        self.cycle_status()

    @on(Button.Pressed, "#refresh-btn")
    def _on_refresh_btn(self) -> None:
        self.cycle_refresh()

    def _emit(self) -> None:
        self.post_message(
            self.FiltersChanged(
                statuses=self._active_statuses(),
                urgencies=list(self._urgencies),
                scope=self._scope,
                status_mode=self._status_mode,
            )
        )


class FieldSelectorScreen(ModalScreen):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "confirm", "Apply"),
    ]

    def __init__(self, visible_columns: list[str]) -> None:
        super().__init__()
        self._visible_columns = set(visible_columns)

    def compose(self) -> ComposeResult:
        with Vertical(id="field-selector-dialog"):
            yield Label("Select columns [dim] space = toggle  ctrl+s = apply  esc = cancel[/dim]")
            selections = [
                Selection(col, col, initial_state=col in self._visible_columns)
                for col in ALL_COLUMNS
            ]
            yield SelectionList(*selections, id="field-selector-list")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        selected = list(self.query_one("#field-selector-list", SelectionList).selected)
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
