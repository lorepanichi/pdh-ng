# pdh-ng

PagerDuty TUI for humans. See [README.md](README.md) for user-facing docs (install, config, keybindings).

## Project layout

```
src/pdh_ng/
├── pd.py             # PagerDuty API wrapper (PagerDuty, Incidents, Users, Services, Teams)
├── config.py         # Config loading/validation — file + env var fallback
├── main.py           # Entry point — loads config and launches TuiApp
└── tui/
    ├── app.py        # TuiApp(App) — holds cfg, UI prefs, logging setup
    ├── screens.py    # IncidentsScreen, IncidentDetailScreen
    ├── widgets.py    # StatusBar, FieldSelectorScreen, SnoozeDialog, ConfirmDialog
    └── styles.tcss   # Textual CSS

tests/
└── test_config.py
```

## Running

```bash
uv sync
uv run pdh-ng
```

## Config loading (`config.py`)

- File: `~/.config/pdh-ng/config.yaml`, env var override: `PDH_NG_CONFIG`
- Required keys: `apikey`, `uid`, `email`
- Env vars `PDH_NG_APIKEY`, `PDH_NG_UID`, `PDH_NG_EMAIL` fill in any keys missing after file load
- File takes precedence over env vars
- Missing keys after both sources → print error + `sys.exit(1)`

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
`StatusBar(Horizontal)` is docked inline (not `dock: bottom`) to avoid overlapping with `Footer`. Contains two cycling buttons:
- `1` / click: cycles scope `mine → team → all`
- `2` / click: cycles status filter `all statuses → triggered → ack'd`

### Scope modes
- `mine`: `pd.incidents.mine()`
- `team`: `pd.users.get(cfg["uid"])` → extract team IDs → `pd.incidents.fetch(teams=[...])`
- `all`: `pd.incidents.fetch()`

### Persistent UI prefs
`TuiApp.visible_columns` property reads/writes `~/.local/state/pdh-ng/ui.yaml`. Any column not in `ALL_COLUMNS` is silently filtered out on load (handles migrations).

### Logging
Single log file at `~/.local/state/pdh-ng/logs/tui.log`. Directory is created on startup if missing.

### Caching
`Users` and `Teams` methods use `@lru_cache()` with a `ttl_hash(seconds=30)` argument to expire every 30s. `Incidents` is never cached — always fetches live.

## Textual version

Currently running **Textual 6.x**. Key API notes:
- `call_from_thread` lives on `App` only, not `Widget`/`Screen`
- `Button(compact=True, flat=True)` for inline status bar buttons
- `ModalScreen.dismiss(value)` passes value to the `push_screen` callback
- Bindings use `Binding(key, action, description, show=False)` to hide from footer

## Dependencies

Managed with **uv**. Key runtime deps: `pagerduty`, `textual>=0.80.0`, `rich`, `pyyaml`, `humanize`. Build backend: `hatchling`.
