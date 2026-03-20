# pdh-ng

**PDH New Generation** is a PagerDuty TUI. See @README for project overview and user-facing docs (install, config, keybindings).

## Project layout

```
src/pdh_ng/
├── pd.py             # PagerDuty API wrapper (PagerDuty, Incidents, Users, Services, Teams)
├── config.py         # Config loading/validation — file + env var fallback + DEFAULTS
├── main.py           # Entry point — loads config and launches TuiApp
└── tui/
    ├── app.py        # TuiApp(App) — holds cfg, UI prefs, logging setup
    ├── constants.py  # IncScope, IncStatus, IncUrgency, RefreshTime enums + cycle/label/API lookup tables
    ├── screens.py    # IncidentsScreen, IncidentDetailScreen
    ├── widgets.py    # StatusBar, ColumnSelectorScreen, SnoozeDialog, ConfirmDialog
    └── styles.tcss   # Textual CSS

tests/
├── test_config.py
├── test_pd.py
└── tui/
    ├── test_app.py
    ├── test_screens.py
    └── test_widgets.py
```

## Running

```sh
uv sync
uv run pdh-ng
```

## Testing

Always run tests after making changes:

```sh
uv run pytest tests/ -q
```

## CLI (`main.py`)

- `-c FILE` / `--config FILE` — use an alternative config file (overrides `PDH_NG_CONFIG` env var)
- If `-c FILE` is given and the file does not exist, print error and exit (default path missing is silently ignored)
- `-d` / `--debug` — force `cfg["log_level"] = "DEBUG"` after config is loaded, overriding the file/env value

## Config loading (`config.py`)

- File: `~/.config/pdh-ng/config.yaml`, overridable via `-c FILE` or env var `PDH_NG_CONFIG`
- Required keys: `apikey`, `uid`, `email`
- Every key (required + optional) can be set via env var `PDH_NG_<KEY_UPPERCASE>` — derived automatically by `_env_var(key)`, no hardcoded map
- File takes precedence over env vars
- Missing required keys after both sources → print error + `sys.exit(1)`
- Invalid YAML or non-mapping root → print error + `sys.exit(1)`
- Optional keys (with defaults in `DEFAULTS` dict, applied after env var fallback):
  - `log_enabled: true`
  - `log_file: ~/.local/state/pdh-ng/logs/tui.log`
  - `log_level: DEBUG`
  - `max_network_attempts: 5`
- `Config` class: `from_yaml`, `__getitem__`, `__setitem__`, `get`, `__contains__`, `__repr__` — no serialisation methods

## Key architecture decisions

### Shared PagerDuty client
`TuiApp` holds a single `PagerDuty` instance at `self.pd`, created in `__init__`. All workers reuse it via `app.pd` — no per-request client construction. `PagerDuty.__init__` calls `/abilities` once (auth check) and nothing else.

### Textual threading
All PagerDuty API calls run in `@work(thread=True)` workers. UI updates from workers must use `app.call_from_thread(...)` where `app` is captured as `app = self.app` at the **very first line** of the worker — before any network calls. `self.app` is a ContextVar lookup that can fail mid-execution after asyncio context changes; a local variable avoids this. Do NOT use `self.call_from_thread()` (moved to App-only in Textual 6).

### Column widths
`DataTable.clear(columns=True)` + `add_columns()` must be called on every reload to prevent stale column widths when data changes.

### Cell markup
`DataTable.add_row()` renders Rich markup automatically. `DataTable.update_cell_at()` does NOT — wrap values with `Text.from_markup()` from `rich.text`.

### Symbols indicator
The first column (`width=3`) is a combined marker rendered by `_row_marker(inc)`, which concatenates three characters:
- Urgency: `▋` (red = high, blue = low) or space — from `_urgency_marker(inc)` (static method)
- Auto-ack: `!` (bold yellow) if the incident is in `_auto_acked_ids`, else space
- Selection: `✓` (bold green) if the incident is in `_selected_ids`, else space

"urgency" is excluded from `ALL_COLUMNS`.

### Cursor and selection persistence
`_populate_table` snapshots `cursor_id` (the incident ID at the current cursor row) before clearing the table, then restores via `table.get_row_index(cursor_id)` + `table.move_cursor()` after repopulating. `_selected_ids` and `_auto_acked_ids` are reconciled with the new dataset (`&=` set intersection) after the loop. Selection state is rendered correctly in the initial `add_row` calls — `_row_marker` checks `_selected_ids` and `_auto_acked_ids` at insert time.

### Status bar
`StatusBar(Horizontal)` is docked inline (not `dock: bottom`) to avoid overlapping with `Footer`. Contains five buttons (styled purely via CSS — no `compact`/`flat`/`variant` args):
- `1` / click: cycles scope `mine → team → all`
- `2` / click: cycles status filter `all statuses → triggered → ack'd`
- `3` / click: cycles urgency filter `all urgencies → high → low`
- `4` / click: toggles auto-ack `4:auto-ack OFF ↔ 4:auto-ack ON`
- `5` / click: cycles auto-refresh interval `↻ off → ↻ 3s → ↻ 5s → ↻ 10s`

The count label shows `N incident(s)` and appends `↻` while a refresh is in progress (preserving the last count).

Each button emits its own message: `ScopeChanged(inc_scope)`, `StatusChanged(inc_status)`, `UrgencyChanged(inc_urgency)`, `AutoAckChanged(auto_ack: bool)`, `RefreshTimeChanged(refresh_time)`. Receivers for filter messages derive API strings via `_INC_STATUS_API[inc_status]` and `_INC_URGENCY_API[inc_urgency]`.

### Scope modes
- `IncScope.MINE`: `pd.incidents.mine()`
- `IncScope.TEAM`: `pd.users.get(cfg["uid"])` → extract team IDs → `pd.incidents.fetch(teams=[...])`
- `IncScope.ALL`: `pd.incidents.fetch()`

### Auto-refresh
`IncidentsScreen` uses a one-shot `set_timer` (not `set_interval`) so the countdown starts **after** the API call finishes. Default interval: 5s. Cycle: off → 3s → 5s → 10s.

`_schedule_next_refresh()` cancels any live timer then arms a new one if `_refresh_time > 0` and not `_suspended`. It is called at the end of `_populate_table`, `_set_error`, and `_on_refresh_time_changed`. Changing the refresh interval reschedules immediately; changing other filters does not.

`on_screen_suspend` sets `_suspended = True` and cancels any live timer. `on_screen_resume` clears `_suspended` and calls `_schedule_next_refresh()`. This stops all API calls while `IncidentDetailScreen` is open.

### Auto-ack
When `_auto_ack` is `True`, `_populate_table` calls `_do_auto_ack(incs)` at the end of every table load. The worker filters the fetched list to incidents where `status == "triggered"` AND the user's `uid` appears in `assignments[*].assignee.id` — regardless of the active scope (mine/team/all). If nothing matches, it returns early. Otherwise it sets `_auto_acked_ids` to the matching IDs, acks them silently, posts a toast via `app.notify()`, then calls `app.call_from_thread(self._populate_table, incs)` directly with the already-fetched list (not `load_incidents()`). On that repopulate, `_row_marker` renders the auto-acked rows with `!`. Stale `_auto_acked_ids` are cleaned up by `_populate_table`'s `&=` intersection on every load.

### Persistent UI prefs
`TuiApp` reads/writes `~/.local/state/pdh-ng/ui.yaml` (path constant: `_PREFS_PATH`). Stored keys:
- `visible_columns` — visible column list (filtered against `ALL_COLUMNS` on load)
- `inc_scope` — stored as int (`IncScope` value)
- `inc_status` — stored as int (`IncStatus` value)
- `inc_urgency` — stored as int (`IncUrgency` value)
- `refresh_time` — stored as int (`RefreshTime` value, i.e. seconds)
- `auto_ack` — stored as bool (default `False`)

All six are r/w properties on `TuiApp`. Setters write to `_prefs` in memory only; `save_prefs()` is called once in `IncidentsScreen.on_unmount`. `inc_scope`, `inc_status`, `inc_urgency`, and `auto_ack` are updated immediately in their respective `_on_*_changed` handlers; `refresh_time` in `_on_refresh_time_changed`.

### Logging
Set up in `TuiApp._setup_logging()` called from `__init__`. Controlled by config keys `log_enabled`, `log_file`, `log_level`. If disabled, adds `NullHandler` to suppress output.

### Caching
`Users` and `Teams` methods cache with a 30s TTL using a two-method pattern: the public method calls `ttl_hash()` at invocation time and passes it to a `@lru_cache`-decorated private method (e.g. `get` → `_get_cached`). This ensures the TTL bucket changes each 30s window and the cache actually expires. Do NOT put `ttl_hash()` as a default argument — default args are evaluated once at import time, so the cache would never expire. `Incidents` is never cached — always fetches live.

### Screen compose vs on_mount
All prefs (`inc_scope`, `inc_status`, `inc_urgency`, `refresh_time`, `auto_ack`, `visible_columns`) are passed to `IncidentsScreen.__init__` by `TuiApp.on_mount`. The screen initialises its fields from these args and does not read `self.app` during `compose()` or `on_mount()`. Event handlers write back to `self.app` to persist state.

### on_unmount caveat
In `on_unmount`, children are already removed — `query_one` will raise `NoMatches`. Track mutable state as screen fields (`self._inc_scope`, `self._inc_status`, `self._inc_urgency`) updated via event handlers. `on_unmount` only calls `self.app.save_prefs()` — it does not write to `_prefs` directly.

## Textual version

Currently running **Textual 8.x** (requires `rich>=14.2.0`). Key API notes:
- `call_from_thread` lives on `App` only, not `Widget`/`Screen`
- `StatusBar` buttons are plain `Button()` — no `compact`/`flat`/`variant`; appearance controlled entirely by TCSS
- `ModalScreen.dismiss(value)` passes value to the `push_screen` callback
- Bindings use `Binding(key, action, description, show=False)` to hide from footer
- `set_timer(interval, cb)` fires once after `interval` seconds (one-shot); `set_interval` is repeating
- `DataTable` (7.5.0+): fires `RowSelected` only when the row is **already highlighted** — clicking an un-highlighted row first highlights it; selection fires on the second click. Handle via `on_data_table_row_selected` method (not `@on` decorator with CSS selector — unreliable in 8.x). `DataTable` consumes `enter` internally so screen-level `enter` bindings are never reached.
- `Static` with `height: auto` inside `ScrollableContainer` does not size correctly in Textual 8.x — lay out `Static` and `DataTable` directly in the `Screen` instead.

## Dependencies

Managed with **uv**. Key runtime deps: `pagerduty`, `textual>=8.1.1`, `rich>=14.2.0`, `pyyaml`, `humanize`. Build backend: `hatchling`.
