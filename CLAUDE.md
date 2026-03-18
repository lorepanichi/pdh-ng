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
    ├── widgets.py    # StatusBar, FieldSelectorScreen, SnoozeDialog, ConfirmDialog
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

## CLI (`main.py`)

- `-c FILE` / `--config FILE` — use an alternative config file (overrides `PDH_NG_CONFIG` env var)
- If `-c FILE` is given and the file does not exist, print error and exit (default path missing is silently ignored)

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

### TUI calls pd.py directly
The TUI constructs `PagerDuty(cfg)` directly and calls `.incidents`, `.users`, `.services`, `.teams` sub-objects.

### Textual threading
All PagerDuty API calls run in `@work(thread=True)` workers. UI updates from workers must use `self.app.call_from_thread(...)` — NOT `self.call_from_thread()` (moved to App-only in Textual 6).

### Column widths
`DataTable.clear(columns=True)` + `add_columns()` must be called on every reload to prevent stale column widths when data changes.

### Cell markup
`DataTable.add_row()` renders Rich markup automatically. `DataTable.update_cell_at()` does NOT — wrap values with `Text.from_markup()` from `rich.text`.

### Urgency indicator
The first column (`width=2`) is a combined marker rendered by `_row_marker(inc, selected)`:
- Always shows urgency `▋` (red = high, blue = low, space = none) plus selection `✓` (green) or space side by side — e.g. `▋✓` or `▋ `.
- `_urgency_marker` returns `" "` (space) for unknown/missing urgency so the cell never collapses.
- "urgency" is excluded from `ALL_COLUMNS`.

### Cursor and selection persistence
`_populate_table` snapshots `cursor_id` (the incident ID at the current cursor row) before clearing the table, then restores via `table.get_row_index(cursor_id)` + `table.move_cursor()` after repopulating. `_selected_ids` is reconciled with the new dataset (`&=` set intersection) rather than cleared, and surviving selections have their marker cells repainted.

### Status bar
`StatusBar(Horizontal)` is docked inline (not `dock: bottom`) to avoid overlapping with `Footer`. Contains four cycling buttons:
- `1` / click: cycles scope `mine → team → all`
- `2` / click: cycles status filter `all statuses → triggered → ack'd`
- `3` / click: cycles auto-refresh interval `↻ off → ↻ 3s → ↻ 5s → ↻ 10s`
- `4` / click: cycles urgency filter `all urgencies → high → low`

The count label shows `N incident(s)` and appends `↻` while a refresh is in progress (preserving the last count).

`FiltersChanged` message carries `inc_scope: IncScope`, `inc_status: IncStatus`, and `inc_urgency: IncUrgency`. Receivers derive API strings via `_INC_STATUS_API[inc_status]` and `_INC_URGENCY_API[inc_urgency]`. `RefreshTimeChanged` carries `refresh_time: RefreshTime`.

### Scope modes
- `IncScope.MINE`: `pd.incidents.mine()`
- `IncScope.TEAM`: `pd.users.get(cfg["uid"])` → extract team IDs → `pd.incidents.fetch(teams=[...])`
- `IncScope.ALL`: `pd.incidents.fetch()`

### Auto-refresh
`IncidentsScreen` uses a one-shot `set_timer` (not `set_interval`) so the countdown starts **after** the API call finishes. Default interval: 5s. Cycle: off → 3s → 5s → 10s. Changing filters resets the timer but does not trigger an immediate reload. Timer is managed via `_schedule_next_refresh()` called at the end of `_populate_table` and `_set_error`.

### Persistent UI prefs
`TuiApp` reads/writes `~/.local/state/pdh-ng/ui.yaml` (path constant: `_PREFS_PATH`). Stored keys:
- `visible_columns` — visible column list (filtered against `ALL_COLUMNS` on load)
- `inc_scope` — stored as int (`IncScope` value)
- `inc_status` — stored as int (`IncStatus` value)
- `inc_urgency` — stored as int (`IncUrgency` value)
- `refresh_time` — stored as int (`RefreshTime` value, i.e. seconds)

All five are r/w properties on `TuiApp`. Setters write to `_prefs` in memory only; `save_prefs()` is called once in `IncidentsScreen.on_unmount`. `inc_scope`, `inc_status`, and `inc_urgency` are updated immediately in `_on_filters_changed`; `refresh_time` in `_on_refresh_time_changed`.

### Logging
Set up in `TuiApp._setup_logging()` called from `__init__`. Controlled by config keys `log_enabled`, `log_file`, `log_level`. If disabled, adds `NullHandler` to suppress output.

### Caching
`Users` and `Teams` methods use `@lru_cache()` with a `ttl_hash(seconds=30)` argument to expire every 30s. `Incidents` is never cached — always fetches live.

### Screen compose vs on_mount
Do NOT access `self.app` inside `IncidentsScreen.compose()` — the screen may be embedded as a widget in tests before the app reference is fully wired. Read all prefs in `on_mount()` instead.

### on_unmount caveat
In `on_unmount`, children are already removed — `query_one` will raise `NoMatches`. Track mutable state as screen fields (`self._inc_scope`, `self._inc_status`, `self._inc_urgency`) updated via event handlers. `on_unmount` only calls `self.app.save_prefs()` — it does not write to `_prefs` directly.

## Textual version

Currently running **Textual 8.x** (requires `rich>=14.2.0`). Key API notes:
- `call_from_thread` lives on `App` only, not `Widget`/`Screen`
- `Button(compact=True, flat=True)` for inline status bar buttons
- `ModalScreen.dismiss(value)` passes value to the `push_screen` callback
- Bindings use `Binding(key, action, description, show=False)` to hide from footer
- `set_timer(interval, cb)` fires once after `interval` seconds (one-shot); `set_interval` is repeating
- `DataTable` (7.5.0+): fires `Selected` only when the row is **already highlighted** — clicking an un-highlighted row first highlights it; selection fires on the second click

## Dependencies

Managed with **uv**. Key runtime deps: `pagerduty`, `textual>=8.1.1`, `rich>=14.2.0`, `pyyaml`, `humanize`. Build backend: `hatchling`.
