from __future__ import annotations

import logging
import webbrowser
from datetime import UTC, datetime

import humanize
from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, Static

from ..pd import STATUS_TRIGGERED
from .constants import (
    _INC_STATUS_API,
    _INC_URGENCY_API,
    IncScope,
    IncStatus,
    IncUrgency,
    RefreshTime,
)
from .widgets import ColumnSelectorScreen, SnoozeDialog, StatusBar

logger = logging.getLogger("pdh-ng")

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
    """Convert an ISO 8601 timestamp to a human-readable relative age string.

    Args:
        created_at: ISO 8601 datetime string (e.g. "2024-01-01T00:00:00Z").

    Returns:
        Human-readable relative time (e.g. "3 hours ago"), or the original
        string if parsing fails.
    """
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return humanize.naturaltime(dt, when=datetime.now(UTC))
    except Exception:
        return created_at


def _colored(text: str, color: str) -> str:
    """Wrap text in Rich color markup tags."""
    return f"[{color}]{text}[/{color}]"


def _apply_title_filter(incs: list[dict], title_filter: str) -> list[dict]:
    """Filter incidents by title substring.

    Args:
        incs: List of incident dicts.
        title_filter: Search term. Prefix with ``!`` to exclude matches.
            Empty string returns all incidents unchanged.

    Returns:
        Filtered list of incident dicts.
    """
    if not title_filter:
        return incs
    if title_filter.startswith("!"):
        term = title_filter[1:].lower()
        return [i for i in incs if term not in i.get("title", "").lower()]
    return [i for i in incs if title_filter.lower() in i.get("title", "").lower()]


def _cell_value(inc: dict, col: str) -> str:
    """Return the formatted cell value for a given incident column.

    Args:
        inc: Incident dict from the PagerDuty API.
        col: Column name (e.g. "title", "status", "age").

    Returns:
        Rich-markup string ready for DataTable insertion.
    """
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


_NAV_KEYS = frozenset({"up", "down", "pageup", "pagedown"})


class IncidentsScreen(Screen):
    BINDINGS = [
        Binding("1", "cycle_scope", "scope filter", show=False),
        Binding("2", "cycle_status", "status filter", show=False),
        Binding("3", "cycle_urgency", "urgency filter", show=False),
        Binding("4", "cycle_auto_ack", "auto-ack toggle", show=False),
        Binding("5", "cycle_refresh", "refresh interval", show=False),
        Binding("i", "inspect", "Inspect"),
        Binding("y", "yank_title", "Yank title"),
        Binding("o", "open_url", "↗"),
        Binding("a", "ack_selected", "Ack"),
        Binding("r", "resolve_selected", "Resolve"),
        Binding("s", "snooze_selected", "Snooze ┃"),
        Binding("space", "toggle_select", "Select"),
        Binding("escape", "clear_or_hide_filter", "Clear ┃"),
        Binding("f", "toggle_filter", "Filter"),
        Binding("c", "select_columns", "Columns ┃"),
    ]

    SUB_TITLE = "Incidents"

    # -- lifecycle --

    def __init__(
        self,
        inc_scope: IncScope = IncScope.MINE,
        inc_status: IncStatus = IncStatus.ALL,
        inc_urgency: IncUrgency = IncUrgency.ALL,
        refresh_time: RefreshTime = RefreshTime.S5,
        auto_ack: bool = False,
        visible_columns: list[str] | None = None,
    ) -> None:
        """Initialise the incidents screen from persisted UI preferences.

        Args:
            inc_scope: Scope filter (mine / team / all).
            inc_status: Status filter (all / triggered / acknowledged).
            inc_urgency: Urgency filter (all / high / low).
            refresh_time: Auto-refresh interval.
            auto_ack: Whether auto-ack is enabled on load.
            visible_columns: Ordered list of column names to display.
        """
        super().__init__()
        self._inc_scope: IncScope = inc_scope
        self._inc_status: IncStatus = inc_status
        self._inc_urgency: IncUrgency = inc_urgency
        self._current_statuses: list[str] = _INC_STATUS_API[inc_status]
        self._current_urgencies: list[str] = _INC_URGENCY_API[inc_urgency]
        self._title_filter: str = ""
        self._incident_ids: list[str] = []
        self._incidents_cache: dict[str, dict] = {}
        self._selected_ids: set[str] = set()
        self._visible_columns: list[str] = visible_columns or []
        self._refresh_time: RefreshTime = refresh_time
        self._refresh_timer: Timer | None = None
        self._suspended: bool = False
        self._auto_ack: bool = auto_ack
        self._auto_acked_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        """Build the incidents screen layout."""
        yield Header()
        yield DataTable(
            id="incidents-table",
            cursor_type="row",
            zebra_stripes=True,
            # this is to make urgency color appear under a cursor highlighted row
            cursor_foreground_priority="renderable",
            show_cursor=False,
        )
        yield Input(
            placeholder="filter title... (!term to exclude) — enter to apply, esc to cancel",
            id="title-filter",
        )
        yield StatusBar(
            id="status-bar",
            inc_scope=self._inc_scope,
            inc_status=self._inc_status,
            inc_urgency=self._inc_urgency,
            refresh_time=self._refresh_time,
            auto_ack=self._auto_ack,
        )
        yield Footer()

    def on_mount(self) -> None:
        """Trigger the initial incident load, while visibles columns are shown."""
        self._rebuild_columns()
        self.load_incidents()

    def on_unmount(self) -> None:
        """Persist UI preferences when the screen is removed."""
        self.app.save_prefs()

    def on_screen_suspend(self) -> None:
        """Pause auto-refresh while a child screen (e.g. detail) is open."""
        self._suspended = True
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def on_screen_resume(self) -> None:
        """Resume auto-refresh when returning from a child screen."""
        self._suspended = False
        self._schedule_next_refresh()

    # -- auto-refresh --

    def _schedule_next_refresh(self) -> None:
        """Cancel any pending refresh timer and arm a new one-shot timer.

        Does nothing if auto-refresh is disabled or the screen is suspended.
        """
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        if self._refresh_time > 0 and not self._suspended:
            self._refresh_timer = self.set_timer(self._refresh_time, self._on_refresh_timer)

    def _on_refresh_timer(self) -> None:
        """Callback fired when the one-shot refresh timer expires."""
        self._refresh_timer = None
        self.load_incidents()

    # -- table / data --

    @staticmethod
    def _urgency_marker(inc: dict) -> str:
        """Return a colored block character representing incident urgency.

        Args:
            inc: Incident dict.

        Returns:
            Rich-markup string: red ``▋`` (high), blue ``▋`` (low), or a space.
        """
        urgency = inc.get("urgency", "")
        if urgency == "high":
            return "[bold red]▋[/bold red]"
        if urgency == "low":
            return "[bold blue]▋[/bold blue]"
        return " "

    def _row_marker(self, inc: dict) -> str:
        """Build the combined three-character marker for the indicator column.

        Args:
            inc: Incident dict.

        Returns:
            Three-character Rich-markup string: urgency + auto-ack + selection.
        """
        inc_id = inc["id"]
        ack = "[bold yellow]![/bold yellow]" if inc_id in self._auto_acked_ids else " "
        sel = "[bold green]✓[/bold green]" if inc_id in self._selected_ids else " "
        return self._urgency_marker(inc) + ack + sel

    def _rebuild_columns(self) -> None:
        """Clear and re-add DataTable columns to reset stale column widths."""
        table = self.query_one("#incidents-table", DataTable)
        table.clear(columns=True)
        table.add_column("", width=3)
        table.add_columns(*self._visible_columns)

    @work(exclusive=True, thread=True)
    def load_incidents(self) -> None:
        """Fetch incidents from the PagerDuty API and populate the table.

        Runs in a background thread. Applies the current scope, status,
        urgency, and title filters. On success calls ``_populate_table``;
        on error calls ``_set_error``.
        """
        app = self.app
        app.call_from_thread(self._set_loading)
        statuses = self._current_statuses
        urgencies = self._current_urgencies
        inc_scope = self._inc_scope
        title_filter = self._title_filter
        pd_client = app.pd
        try:
            if inc_scope == IncScope.MINE:
                incs = list(pd_client.incidents.mine(statuses=statuses, urgencies=urgencies))
            elif inc_scope == IncScope.TEAM:
                user = pd_client.users.get(app.cfg["uid"])
                team_ids = [t["id"] for t in user.get("teams", [])]
                incs = list(
                    pd_client.incidents.fetch(
                        statuses=statuses, urgencies=urgencies, teams=team_ids
                    )
                )
            else:
                incs = list(pd_client.incidents.fetch(statuses=statuses, urgencies=urgencies))
            incs = _apply_title_filter(incs, title_filter)
            app.call_from_thread(self._populate_table, incs)
        except Exception as e:
            logger.exception("Error loading incidents")
            app.call_from_thread(self._set_error, str(e))

    def _set_loading(self) -> None:
        """Tell the status bar that a fetch is in progress."""
        self.query_one("#status-bar", StatusBar).set_loading()

    def _set_error(self, message: str) -> None:
        """Display an error message in the status bar and reschedule refresh.

        Args:
            message: Error description to show.
        """
        self.query_one("#status-bar", StatusBar).set_error(message)
        self._schedule_next_refresh()

    def _populate_table(self, incs: list) -> None:
        """Populate the DataTable from a list of incidents.

        Preserves cursor position by incident ID across reloads.
        cursor_row is always set, so show_cursor doubles as a guard: when False,
        the cursor is hidden and any action on the pointed row is suppressed.

        Reconciles ``_selected_ids`` and ``_auto_acked_ids`` against the
        new dataset, then schedules the next refresh.

        Args:
            incs: List of incident dicts to display.
        """
        table = self.query_one("#incidents-table", DataTable)

        # capture the incident that the row cursor is pointing to.
        # invariant: show_cursor implies _incident_ids is populated
        cursor_id = self._incident_ids[table.cursor_row] if table.show_cursor else None

        # rebuild columns to reset widths. This also reset the table.
        self._rebuild_columns()
        self._incident_ids = []
        self._incidents_cache = {}

        for inc in sorted(incs, key=lambda i: i.get("created_at", "")):
            inc_id = inc["id"]
            self._incident_ids.append(inc_id)
            self._incidents_cache[inc_id] = inc
            cells = [_cell_value(inc, col) for col in self._visible_columns]
            table.add_row(self._row_marker(inc), *cells, key=inc_id)

        # remove stale incident IDs
        self._selected_ids &= set(self._incident_ids)
        self._auto_acked_ids &= set(self._incident_ids)

        # keep the row cursor on the same incident
        if cursor_id in self._incidents_cache:
            try:
                table.move_cursor(row=table.get_row_index(cursor_id), scroll=True)
            except Exception:
                pass
        else:
            # Cursor incident no longer exists, or there was no prior cursor.
            table.show_cursor = False

        # update status bar
        self.query_one("#status-bar", StatusBar).set_status(
            inc_count=len(incs),
            title_filter=self._title_filter,
        )

        self._schedule_next_refresh()
        if self._auto_ack:
            self._do_auto_ack(incs)

    # -- event handlers --

    def on_key(self, event: events.Key) -> None:
        """Re-enable the cursor on navigation keys when it was hidden."""
        if event.key in _NAV_KEYS:
            table = self.query_one("#incidents-table", DataTable)
            if not table.show_cursor and self._incident_ids:
                table.show_cursor = True

    @on(events.Click, "#incidents-table")
    def on_incidents_table_click(self, event: events.Click) -> None:
        """Re-enable the cursor when the user clicks a row while it is hidden."""
        table = self.query_one("#incidents-table", DataTable)
        if table.show_cursor or not self._incident_ids:
            return
        row_index = event.style.meta.get("row", -1)
        if 0 <= row_index < len(self._incident_ids):
            table.show_cursor = True
            table.move_cursor(row=row_index, scroll=True)

    @on(StatusBar.ScopeChanged)
    def _on_scope_changed(self, event: StatusBar.ScopeChanged) -> None:
        """Handle scope filter changes from the status bar."""
        self._inc_scope = event.inc_scope
        self.app.inc_scope = event.inc_scope

    @on(StatusBar.StatusChanged)
    def _on_status_changed(self, event: StatusBar.StatusChanged) -> None:
        """Handle status filter changes from the status bar."""
        self._inc_status = event.inc_status
        self._current_statuses = _INC_STATUS_API[event.inc_status]
        self.app.inc_status = event.inc_status

    @on(StatusBar.UrgencyChanged)
    def _on_urgency_changed(self, event: StatusBar.UrgencyChanged) -> None:
        """Handle urgency filter changes from the status bar."""
        self._inc_urgency = event.inc_urgency
        self._current_urgencies = _INC_URGENCY_API[event.inc_urgency]
        self.app.inc_urgency = event.inc_urgency

    @on(StatusBar.RefreshTimeChanged)
    def _on_refresh_time_changed(self, event: StatusBar.RefreshTimeChanged) -> None:
        """Handle refresh-interval changes and reschedule the refresh timer."""
        self._refresh_time = event.refresh_time
        self.app.refresh_time = event.refresh_time
        self._schedule_next_refresh()

    @on(StatusBar.AutoAckChanged)
    def _on_auto_ack_changed(self, event: StatusBar.AutoAckChanged) -> None:
        """Handle auto-ack toggle changes from the status bar."""
        self._auto_ack = event.auto_ack
        self.app.auto_ack = event.auto_ack

    @on(Input.Submitted, "#title-filter")
    def _on_title_filter_submitted(self, event: Input.Submitted) -> None:
        """Apply the submitted title filter and reload incidents."""
        self._title_filter = event.value
        self.query_one("#title-filter", Input).display = False
        self.query_one("#incidents-table").focus()
        self.load_incidents()

    # -- actions: filter controls --

    def action_cycle_scope(self) -> None:
        """Cycle the scope filter: mine → team → all."""
        self.query_one("#status-bar", StatusBar).cycle_scope()

    def action_cycle_status(self) -> None:
        """Cycle the status filter: all → triggered → acknowledged."""
        self.query_one("#status-bar", StatusBar).cycle_status()

    def action_cycle_urgency(self) -> None:
        """Cycle the urgency filter: all → high → low."""
        self.query_one("#status-bar", StatusBar).cycle_urgency()

    def action_cycle_auto_ack(self) -> None:
        """Toggle auto-ack on/off."""
        self.query_one("#status-bar", StatusBar).toggle_auto_ack()

    def action_cycle_refresh(self) -> None:
        """Cycle the auto-refresh interval: off → 3s → 5s → 10s."""
        self.query_one("#status-bar", StatusBar).cycle_refresh()

    def action_toggle_filter(self) -> None:
        """Show or hide the title filter input."""
        filter_input = self.query_one("#title-filter", Input)
        filter_input.display = not filter_input.display
        if filter_input.display:
            filter_input.value = self._title_filter
            filter_input.focus()
        else:
            self.query_one("#incidents-table").focus()

    def action_clear_or_hide_filter(self) -> None:
        """Hide the title filter if visible; otherwise clear row selection."""
        # this action is multipurpose:
        # - if the title filter is visibile, reset
        # - otherwise is an incident de-selection
        filter_input = self.query_one("#title-filter", Input)
        if filter_input.display:
            filter_input.display = False
            self.query_one("#incidents-table").focus()
            return
        if self._selected_ids:
            self._selected_ids.clear()
            table = self.query_one("#incidents-table", DataTable)
            for i, inc_id in enumerate(self._incident_ids):
                inc = self._incidents_cache[inc_id]
                table.update_cell_at(Coordinate(i, 0), self._row_marker(inc))

    def action_toggle_select(self) -> None:
        """Toggle selection on the row under the cursor."""
        table = self.query_one("#incidents-table", DataTable)
        row_idx = table.cursor_row
        if table.show_cursor:
            inc_id = self._incident_ids[row_idx]
            if inc_id in self._selected_ids:
                self._selected_ids.discard(inc_id)
            else:
                self._selected_ids.add(inc_id)
            inc = self._incidents_cache[inc_id]
            table.update_cell_at(Coordinate(row_idx, 0), self._row_marker(inc))

    def action_select_columns(self) -> None:
        """Open the column selector modal."""
        self.app.push_screen(
            ColumnSelectorScreen(self._visible_columns),
            self._apply_column_selection,
        )

    def _apply_column_selection(self, selected: list[str] | None) -> None:
        """Apply the column list returned by the column selector modal.

        Args:
            selected: New ordered column list, or ``None`` if the modal was dismissed.
        """
        if selected is None:
            return
        self._visible_columns = selected
        self.app.visible_columns = selected
        self._populate_table(list(self._incidents_cache.values()))

    def action_inspect(self) -> None:
        """Open the detail screen for the incident under the cursor."""
        table = self.query_one("#incidents-table", DataTable)
        if table.show_cursor:
            inc_id = self._incident_ids[table.cursor_row]
            inc = self._incidents_cache.get(inc_id)
            if inc is not None:
                self.app.push_screen(IncidentDetailScreen(inc))

    def action_yank_title(self) -> None:
        """Copy the title of the incident under the cursor to the clipboard."""
        table = self.query_one("#incidents-table", DataTable)
        if table.show_cursor:
            inc = self._incidents_cache.get(self._incident_ids[table.cursor_row])
            if inc:
                self.app.copy_to_clipboard(inc.get("title", ""))
                self.notify("Title copied")

    def action_open_url(self) -> None:
        """Open the PagerDuty web URL of the incident under the cursor."""
        table = self.query_one("#incidents-table", DataTable)
        if table.show_cursor:
            inc = self._incidents_cache.get(self._incident_ids[table.cursor_row])
            if inc:
                url = inc.get("html_url", "")
                if url:
                    webbrowser.open(url)

    # -- actions: incident mutations --

    def _get_target_incs(self) -> list[dict]:
        """Return the list of incidents to act on.

        Returns:
            Selected incidents if any are selected, otherwise a single-element
            list with the incident under the cursor. Empty list if no incidents.
        """
        if self._selected_ids:
            return [self._incidents_cache[i] for i in self._selected_ids]
        table = self.query_one("#incidents-table", DataTable)
        if table.show_cursor:
            inc_id = self._incident_ids[table.cursor_row]
            return [self._incidents_cache[inc_id]]
        return []

    def action_ack_selected(self) -> None:
        """Acknowledge the target incident(s)."""
        incs = self._get_target_incs()
        if incs:
            self._do_ack(incs)

    @work(thread=True)
    def _do_ack(self, incs: list[dict]) -> None:
        """Acknowledge incidents via the PagerDuty API.

        Runs in a background thread. On success repopulates the table from
        cache without a network round-trip.

        Args:
            incs: List of incident dicts to acknowledge.
        """
        app = self.app
        try:
            app.pd.incidents.ack(incs)
            logger.debug("Acked %d incidents", len(incs))
            app.call_from_thread(app.notify, f"Acknowledged {len(incs)} incident(s)")
            app.call_from_thread(self._populate_table, list(self._incidents_cache.values()))
        except Exception as e:
            logger.exception("Error acking incidents")
            app.call_from_thread(self._set_error, str(e))

    def action_resolve_selected(self) -> None:
        """Resolve the target incident(s)."""
        incs = self._get_target_incs()
        if incs:
            self._do_resolve(incs)

    @work(thread=True)
    def _do_resolve(self, incs: list[dict]) -> None:
        """Resolve incidents via the PagerDuty API.

        Runs in a background thread. On success triggers a full reload.

        Args:
            incs: List of incident dicts to resolve.
        """
        app = self.app
        try:
            app.pd.incidents.resolve(incs)
            logger.debug("Resolved %d incidents", len(incs))
        except Exception as e:
            logger.exception("Error resolving incidents")
            app.call_from_thread(self._set_error, str(e))
            return
        app.call_from_thread(self.load_incidents)

    def action_snooze_selected(self) -> None:
        """Open the snooze dialog for the target incident(s)."""
        incs = self._get_target_incs()
        if incs:
            self.app.push_screen(
                SnoozeDialog(),
                lambda duration: self._do_snooze(incs, duration) if duration else None,
            )

    @work(thread=True)
    def _do_snooze(self, incs: list[dict], duration: int) -> None:
        """Snooze incidents via the PagerDuty API.

        Runs in a background thread. On success triggers a full reload.

        Args:
            incs: List of incident dicts to snooze.
            duration: Snooze duration in seconds.
        """
        app = self.app
        try:
            app.pd.incidents.snooze(incs, duration)
            logger.debug("Snoozed %d incidents for %ds", len(incs), duration)
        except Exception as e:
            logger.exception("Error snoozing incidents")
            app.call_from_thread(self._set_error, str(e))
            return
        app.call_from_thread(self.load_incidents)

    @work(thread=True)
    def _do_auto_ack(self, incs: list[dict]) -> None:
        """Automatically acknowledge triggered incidents assigned to the current user.

        Runs in a background thread. Filters ``incs`` to triggered incidents
        where the configured ``uid`` appears in the assignees list, regardless
        of the active scope. Updates ``_auto_acked_ids`` and repopulates the
        table without a network round-trip.

        Args:
            incs: Full incident list from the most recent fetch.
        """
        app = self.app
        uid = app.cfg["uid"]
        to_ack = [
            inc
            for inc in incs
            if inc.get("status") == STATUS_TRIGGERED
            and any(a["assignee"]["id"] == uid for a in inc.get("assignments", []))
        ]
        if not to_ack:
            return
        self._auto_acked_ids = {inc["id"] for inc in to_ack}
        try:
            app.pd.incidents.ack(to_ack)
            logger.debug("Auto-acked %d incidents", len(to_ack))
        except Exception as e:
            logger.exception("Error auto-acking incidents")
            app.call_from_thread(self._set_error, str(e))
            return
        app.call_from_thread(
            app.notify, f"! Auto-acked {len(to_ack)} incident(s)", severity="warning"
        )
        app.call_from_thread(self._populate_table, incs)


class IncidentDetailScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, inc: dict) -> None:
        """Initialise the detail screen for a single incident.

        Args:
            inc: Incident dict from the PagerDuty API.
        """
        super().__init__()
        self._inc = inc

    def compose(self) -> ComposeResult:
        """Build the incident detail layout."""
        yield Header()
        yield Static(id="incident-info")
        yield DataTable(id="alerts-table", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        """Set up the alerts table columns, render incident info, and load alerts."""
        table = self.query_one("#alerts-table", DataTable)
        table.add_columns("ID", "Summary", "Status", "Age")
        self._populate_info(self._inc)
        self.load_alerts()

    def _populate_info(self, inc: dict) -> None:
        """Render incident metadata into the info Static widget.

        Args:
            inc: Incident dict to display.
        """
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

    @work(exclusive=True, thread=True)
    def load_alerts(self) -> None:
        """Fetch and display alerts for the current incident."""
        app = self.app
        try:
            alerts_data = app.pd.incidents.alerts(self._inc["id"])
            alerts = alerts_data if isinstance(alerts_data, list) else alerts_data.get("alerts", [])
            app.call_from_thread(self._populate_alerts, alerts)
        except Exception:
            logger.exception("Error loading alerts")

    def _populate_alerts(self, alerts: list) -> None:
        """Populate the alerts DataTable.

        Args:
            alerts: List of alert dicts from the PagerDuty API.
        """
        table = self.query_one("#alerts-table", DataTable)
        for alert in alerts:
            table.add_row(
                alert.get("id", ""),
                alert.get("summary", ""),
                alert.get("status", ""),
                _fmt_age(alert.get("created_at", "")),
            )
