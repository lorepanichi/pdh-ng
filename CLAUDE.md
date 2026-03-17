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
Urgency is shown as a coloured `▋` in the first (marker) column instead of a separate urgency column. `▋` red = high, blue = low. Turns to a bright-coloured `✓` on selection (colour preserved). "urgency" is excluded from `ALL_COLUMNS`.

### Status bar
`StatusBar(Horizontal)` is docked inline (not `dock: bottom`) to avoid overlapping with `Footer`. Contains three cycling buttons:
- `1` / click: cycles scope `mine → team → all`
- `2` / click: cycles status filter `all statuses → triggered → ack'd`
- `3` / click: cycles auto-refresh interval `↻ off → ↻ 3s → ↻ 5s → ↻ 10s`

The count label shows `N incident(s)` and appends `↻` while a refresh is in progress (preserving the last count).

`FiltersChanged` message carries `statuses`, `urgencies`, `scope`, and `status_mode`.

### Scope modes
- `mine`: `pd.incidents.mine()`
- `team`: `pd.users.get(cfg["uid"])` → extract team IDs → `pd.incidents.fetch(teams=[...])`
- `all`: `pd.incidents.fetch()`

### Auto-refresh
`IncidentsScreen` uses a one-shot `set_timer` (not `set_interval`) so the countdown starts **after** the API call finishes. Default interval: 5s. Cycle: off → 3s → 5s → 10s. Changing filters resets the timer but does not trigger an immediate reload. Timer is managed via `_schedule_next_refresh()` called at the end of `_populate_table` and `_set_error`.

### Persistent UI prefs
`TuiApp` reads/writes `~/.local/state/pdh-ng/ui.yaml` (path constant: `_PREFS_PATH`). Stored keys:
- `columns` — visible column list (filtered against `ALL_COLUMNS` on load)
- `refresh_interval` — saved on every change
- `scope` — saved on app exit (`IncidentsScreen.on_unmount`)
- `status_mode` — saved on app exit (`IncidentsScreen.on_unmount`)

`TuiApp` exposes: `visible_columns` (r/w property), `refresh_interval` (r/w property), `scope` (r/o property), `status_mode` (r/o property).

### Logging
Set up in `TuiApp._setup_logging()` called from `__init__`. Controlled by config keys `log_enabled`, `log_file`, `log_level`. If disabled, adds `NullHandler` to suppress output.

### Caching
`Users` and `Teams` methods use `@lru_cache()` with a `ttl_hash(seconds=30)` argument to expire every 30s. `Incidents` is never cached — always fetches live.

### Screen compose vs on_mount
Do NOT access `self.app` inside `IncidentsScreen.compose()` — the screen may be embedded as a widget in tests before the app reference is fully wired. Read all prefs in `on_mount()` instead.

### on_unmount caveat
In `on_unmount`, children are already removed — `query_one` will raise `NoMatches`. Track mutable state as screen fields (`self._scope`, `self._status_mode`) updated via event handlers, and save those directly in `on_unmount`.

## Textual version

Currently running **Textual 6.x**. Key API notes:
- `call_from_thread` lives on `App` only, not `Widget`/`Screen`
- `Button(compact=True, flat=True)` for inline status bar buttons
- `ModalScreen.dismiss(value)` passes value to the `push_screen` callback
- Bindings use `Binding(key, action, description, show=False)` to hide from footer
- `set_timer(interval, cb)` fires once after `interval` seconds (one-shot); `set_interval` is repeating

## Dependencies

Managed with **uv**. Key runtime deps: `pagerduty`, `textual>=0.80.0`, `rich`, `pyyaml`, `humanize`. Build backend: `hatchling`.
