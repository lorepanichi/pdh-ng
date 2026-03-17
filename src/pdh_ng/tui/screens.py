from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import humanize
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, Static

from ..pd import STATUS_ACK, STATUS_TRIGGERED, PagerDuty
from .widgets import ConfirmDialog, FieldSelectorScreen, SnoozeDialog, StatusBar

logger = logging.getLogger("pdh-ng.tui")

_STATUS_COLORS = {
    "triggered": "red",
    "acknowledged": "yellow",
    "resolved": "green",
}

_URGENCY_COLORS = {
    "high": "red",
    "low": "blue",
}


def _fmt_age(created_at: str) -> str:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return humanize.naturaltime(dt, when=datetime.now(UTC))
    except Exception:
        return created_at


def _colored(text: str, color: str) -> str:
    return f"[{color}]{text}[/{color}]"


def _apply_title_filter(incs: list[dict], title_filter: str) -> list[dict]:
    if not title_filter:
        return incs
    if title_filter.startswith("!"):
        term = title_filter[1:].lower()
        return [i for i in incs if term not in i.get("title", "").lower()]
    return [i for i in incs if title_filter.lower() in i.get("title", "").lower()]


def _urgency_marker(inc: dict) -> str:
    urgency = inc.get("urgency", "")
    if urgency == "high":
        return "[bold red]▋[/bold red]"
    if urgency == "low":
        return "[bold blue]▋[/bold blue]"
    return ""


def _cell_value(inc: dict, col: str) -> str:
    match col:
        case "id":
            return inc.get("id", "")
        case "title":
            return inc.get("title", "")
        case "status":
            s = inc.get("status", "")
            return _colored(s, _STATUS_COLORS.get(s, "white"))
        case "urgency":
            u = inc.get("urgency", "")
            return _colored(u, _URGENCY_COLORS.get(u, "white"))
        case "assignee":
            return ", ".join(a["assignee"]["summary"] for a in inc.get("assignments", []))
        case "service":
            return inc.get("service", {}).get("summary", "")
        case "age":
            return _fmt_age(inc.get("created_at", ""))
        case _:
            return ""


class IncidentsScreen(Screen):
    BINDINGS = [
        Binding("1", "cycle_scope", "scope filter", show=False),
        Binding("2", "cycle_status", "status filter", show=False),
        Binding("3", "cycle_refresh", "refresh interval", show=False),
        ("a", "ack_selected", "Ack"),
        ("r", "resolve_selected", "Resolve"),
        ("s", "snooze_selected", "Snooze"),
        ("space", "toggle_select", "Select"),
        ("escape", "clear_or_hide_filter", "Clear"),
        ("enter", "open_detail", "Detail"),
        ("f", "toggle_filter", "Filter"),
        ("c", "select_columns", "Columns"),
    ]

    SUB_TITLE = "Incidents"

    def __init__(self, show_all: bool = False) -> None:
        super().__init__()
        self._show_all = show_all
        self._scope: str = "all" if show_all else "mine"
        self._current_statuses: list[str] = [STATUS_TRIGGERED, STATUS_ACK]
        self._current_urgencies: list[str] = ["high", "low"]
        self._title_filter: str = ""
        self._incident_ids: list[str] = []
        self._incidents_cache: dict[str, dict] = {}
        self._selected_ids: set[str] = set()
        self._visible_columns: list[str] = []  # loaded from app prefs on mount
        self._status_mode: str = "all"
        self._refresh_interval: int = 5
        self._refresh_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="incidents-table", cursor_type="row", zebra_stripes=True)
        yield Input(placeholder="filter title... (!term to exclude) — enter to apply, esc to cancel", id="title-filter")
        yield StatusBar(scope=self._scope, id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        bar = self.query_one("#status-bar", StatusBar)
        if not self._show_all:
            bar._scope = self.app.scope
        bar._status_mode = self.app.status_mode
        bar._refresh_interval = self.app.refresh_interval
        bar._sync_buttons()
        self._scope = bar._scope
        self._status_mode = bar._status_mode
        self._current_statuses = bar._active_statuses()
        self._visible_columns = self.app.visible_columns
        self._refresh_interval = bar._refresh_interval
        self.query_one("#title-filter").display = False
        self._rebuild_columns()
        self.load_incidents()

    def on_unmount(self) -> None:
        self.app._prefs["scope"] = self._scope
        self.app._prefs["status_mode"] = self._status_mode
        self.app.save_prefs()

    def _schedule_next_refresh(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        if self._refresh_interval > 0:
            self._refresh_timer = self.set_timer(self._refresh_interval, self._on_refresh_timer)

    def _on_refresh_timer(self) -> None:
        self._refresh_timer = None
        self.load_incidents()

    def _start_refresh(self, interval: int) -> None:
        self._refresh_interval = interval
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        if interval > 0:
            self._refresh_timer = self.set_timer(interval, self._on_refresh_timer)

    def _rebuild_columns(self) -> None:
        table = self.query_one("#incidents-table", DataTable)
        table.clear(columns=True)
        table.add_columns("", *self._visible_columns)

    @on(StatusBar.FiltersChanged)
    def _on_filters_changed(self, event: StatusBar.FiltersChanged) -> None:
        self._current_statuses = event.statuses
        self._current_urgencies = event.urgencies
        self._scope = event.scope
        self._status_mode = event.status_mode
        self._schedule_next_refresh()

    @on(Input.Submitted, "#title-filter")
    def _on_title_filter_submitted(self, event: Input.Submitted) -> None:
        self._title_filter = event.value
        self.query_one("#title-filter", Input).display = False
        self.query_one("#incidents-table").focus()
        self.load_incidents()

    @work(exclusive=True, thread=True)
    def load_incidents(self) -> None:
        self.app.call_from_thread(self._set_loading)
        statuses = self._current_statuses
        urgencies = self._current_urgencies
        scope = self._scope
        title_filter = self._title_filter
        cfg = self.app.cfg
        try:
            pd_client = PagerDuty(cfg)
            if scope == "mine":
                incs = list(pd_client.incidents.mine(statuses=statuses, urgencies=urgencies))
            elif scope == "team":
                user = pd_client.users.get(cfg["uid"])
                team_ids = [t["id"] for t in user.get("teams", [])]
                incs = list(
                    pd_client.incidents.fetch(
                        statuses=statuses, urgencies=urgencies, teams=team_ids
                    )
                )
            else:
                incs = list(pd_client.incidents.fetch(statuses=statuses, urgencies=urgencies))
            incs = _apply_title_filter(incs, title_filter)
            self.app.call_from_thread(self._populate_table, incs, scope, title_filter)
        except Exception as e:
            logger.exception("Error loading incidents")
            self.app.call_from_thread(self._set_error, str(e))

    def _set_loading(self) -> None:
        self.query_one("#status-bar", StatusBar).set_loading()

    def _set_error(self, message: str) -> None:
        self.query_one("#status-bar", StatusBar).set_error(message)
        self._schedule_next_refresh()

    def _populate_table(self, incs: list, scope: str, title_filter: str) -> None:
        table = self.query_one("#incidents-table", DataTable)
        table.clear(columns=True)
        table.add_columns("", *self._visible_columns)
        self._incident_ids = []
        self._incidents_cache = {}
        self._selected_ids.clear()

        for inc in incs:
            inc_id = inc["id"]
            self._incident_ids.append(inc_id)
            self._incidents_cache[inc_id] = inc
            cells = [_cell_value(inc, col) for col in self._visible_columns]
            table.add_row(_urgency_marker(inc), *cells, key=inc_id)

        self.query_one("#status-bar", StatusBar).set_count(len(incs), title_filter, scope)
        self._schedule_next_refresh()

    def _get_target_incs(self) -> list[dict]:
        if self._selected_ids:
            return [
                self._incidents_cache[i] for i in self._selected_ids if i in self._incidents_cache
            ]
        table = self.query_one("#incidents-table", DataTable)
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self._incident_ids):
            inc_id = self._incident_ids[row_idx]
            if inc_id in self._incidents_cache:
                return [self._incidents_cache[inc_id]]
        return []

    def action_toggle_select(self) -> None:
        table = self.query_one("#incidents-table", DataTable)
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self._incident_ids):
            inc_id = self._incident_ids[row_idx]
            if inc_id in self._selected_ids:
                self._selected_ids.discard(inc_id)
                marker = _urgency_marker(self._incidents_cache.get(inc_id, {}))
                table.update_cell_at(Coordinate(row_idx, 0), marker)
            else:
                self._selected_ids.add(inc_id)
                table.update_cell_at(Coordinate(row_idx, 0), "[bold green]✓[/bold green]")

    def action_clear_or_hide_filter(self) -> None:
        filter_input = self.query_one("#title-filter", Input)
        if filter_input.display:
            filter_input.display = False
            self.query_one("#incidents-table").focus()
            return
        if self._selected_ids:
            self._selected_ids.clear()
            table = self.query_one("#incidents-table", DataTable)
            for i, inc_id in enumerate(self._incident_ids):
                marker = _urgency_marker(self._incidents_cache.get(inc_id, {}))
                table.update_cell_at(Coordinate(i, 0), marker)

    def action_toggle_filter(self) -> None:
        filter_input = self.query_one("#title-filter", Input)
        filter_input.display = not filter_input.display
        if filter_input.display:
            filter_input.value = self._title_filter
            filter_input.focus()
        else:
            self.query_one("#incidents-table").focus()

    def action_select_columns(self) -> None:
        self.app.push_screen(
            FieldSelectorScreen(self._visible_columns),
            self._apply_column_selection,
        )

    def _apply_column_selection(self, selected: list[str] | None) -> None:
        if selected is None:
            return
        self._visible_columns = selected
        self.app.visible_columns = selected
        self._rebuild_columns()
        self._populate_table(
            list(self._incidents_cache.values()),
            self._scope,
            self._title_filter,
        )

    def action_ack_selected(self) -> None:
        incs = self._get_target_incs()
        if incs:
            self.app.push_screen(
                ConfirmDialog(f"Acknowledge {len(incs)} incident(s)?"),
                lambda confirmed: self._do_ack(incs) if confirmed else None,
            )

    def action_resolve_selected(self) -> None:
        incs = self._get_target_incs()
        if incs:
            self.app.push_screen(
                ConfirmDialog(f"Resolve {len(incs)} incident(s)?"),
                lambda confirmed: self._do_resolve(incs) if confirmed else None,
            )

    def action_snooze_selected(self) -> None:
        incs = self._get_target_incs()
        if incs:
            self.app.push_screen(
                SnoozeDialog(),
                lambda duration: self._do_snooze(incs, duration) if duration else None,
            )

    def action_open_detail(self) -> None:
        filter_input = self.query_one("#title-filter", Input)
        if filter_input.display and filter_input.has_focus:
            return
        table = self.query_one("#incidents-table", DataTable)
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self._incident_ids):
            self.app.push_screen(IncidentDetailScreen(self._incident_ids[row_idx]))

    def action_cycle_scope(self) -> None:
        self.query_one("#status-bar", StatusBar).cycle_scope()

    def action_cycle_status(self) -> None:
        self.query_one("#status-bar", StatusBar).cycle_status()

    def action_cycle_refresh(self) -> None:
        self.query_one("#status-bar", StatusBar).cycle_refresh()

    @on(StatusBar.RefreshIntervalChanged)
    def _on_refresh_interval_changed(self, event: StatusBar.RefreshIntervalChanged) -> None:
        self._start_refresh(event.interval)
        self.app.refresh_interval = event.interval

    @work(thread=True)
    def _do_ack(self, incs: list[dict]) -> None:
        cfg = self.app.cfg
        try:
            PagerDuty(cfg).incidents.ack(incs)
            logger.info("Acked %d incidents", len(incs))
        except Exception as e:
            logger.exception("Error acking incidents")
            self.app.call_from_thread(self._set_error, str(e))
            return
        self.app.call_from_thread(self.load_incidents)

    @work(thread=True)
    def _do_resolve(self, incs: list[dict]) -> None:
        cfg = self.app.cfg
        try:
            PagerDuty(cfg).incidents.resolve(incs)
            logger.info("Resolved %d incidents", len(incs))
        except Exception as e:
            logger.exception("Error resolving incidents")
            self.app.call_from_thread(self._set_error, str(e))
            return
        self.app.call_from_thread(self.load_incidents)

    @work(thread=True)
    def _do_snooze(self, incs: list[dict], duration: int) -> None:
        cfg = self.app.cfg
        try:
            PagerDuty(cfg).incidents.snooze(incs, duration)
            logger.info("Snoozed %d incidents for %ds", len(incs), duration)
        except Exception as e:
            logger.exception("Error snoozing incidents")
            self.app.call_from_thread(self._set_error, str(e))
            return
        self.app.call_from_thread(self.load_incidents)


class IncidentDetailScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, incident_id: str) -> None:
        super().__init__()
        self._incident_id = incident_id

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer():
            yield Static(id="incident-info")
            yield DataTable(id="alerts-table", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#alerts-table", DataTable)
        table.add_columns("ID", "Summary", "Status", "Age")
        self.load_detail()

    @work(exclusive=True, thread=True)
    def load_detail(self) -> None:
        cfg = self.app.cfg
        try:
            pd_client = PagerDuty(cfg)
            inc = pd_client.incidents.get(self._incident_id)
            alerts_data = pd_client.incidents.alerts(self._incident_id)
            self.app.call_from_thread(self._populate_detail, inc, alerts_data)
        except Exception as e:
            logger.exception("Error loading incident detail")
            self.app.call_from_thread(
                self.query_one("#incident-info", Static).update,
                f"[red]Error loading incident: {e}[/red]",
            )

    def _populate_detail(self, inc: dict, alerts_data: Any) -> None:
        status = inc.get("status", "")
        urgency = inc.get("urgency", "")
        assignees = ", ".join(a["assignee"]["summary"] for a in inc.get("assignments", []))
        service = inc.get("service", {}).get("summary", "")
        url = inc.get("html_url", "")
        age = _fmt_age(inc.get("created_at", ""))

        info = (
            f"[bold]{inc.get('title', '')}[/bold]\n\n"
            f"[cyan]ID:[/cyan]       {inc['id']}\n"
            f"[cyan]Status:[/cyan]   {_colored(status, _STATUS_COLORS.get(status, 'white'))}\n"
            f"[cyan]Urgency:[/cyan]  {_colored(urgency, _URGENCY_COLORS.get(urgency, 'white'))}\n"
            f"[cyan]Assignee:[/cyan] {assignees}\n"
            f"[cyan]Service:[/cyan]  {service}\n"
            f"[cyan]Age:[/cyan]      {age}\n"
            f"[cyan]URL:[/cyan]      {url}\n"
        )
        self.query_one("#incident-info", Static).update(info)

        table = self.query_one("#alerts-table", DataTable)
        alerts = alerts_data if isinstance(alerts_data, list) else alerts_data.get("alerts", [])
        for alert in alerts:
            table.add_row(
                alert.get("id", ""),
                alert.get("summary", ""),
                alert.get("status", ""),
                _fmt_age(alert.get("created_at", "")),
            )
