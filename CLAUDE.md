# pdh-ng

PagerDuty TUI. See @README for project overview and user-facing docs (install, config, keybindings).

## Commands

```sh
uv run pdh-ng            # run the app
uv run pytest tests/ -q  # always run after making changes
```

## Non-obvious gotchas

### Textual threading
In `@work(thread=True)` workers, capture `app = self.app` as the **very first line**, before any network calls. `self.app` is a ContextVar that can fail mid-execution after asyncio context switches. Use `app.call_from_thread(...)` — `call_from_thread` is on `App` only, not `Widget`/`Screen` (moved in Textual 6).

### DataTable quirks (Textual 8.x)
- Call `DataTable.clear(columns=True)` + `add_columns()` on every reload — skipping this causes stale column widths.
- `add_row()` renders Rich markup; `update_cell_at()` does NOT — wrap values with `Text.from_markup()`.
- `RowSelected` fires only when the row is already highlighted (first click highlights, second selects). Handle via `on_data_table_row_selected` method — `@on` decorator with CSS selector is unreliable in 8.x.
- `DataTable` consumes `enter`, so screen-level `enter` bindings are never reached.
- `Static` with `height: auto` inside `ScrollableContainer` doesn't size correctly — put `Static` and `DataTable` directly in the `Screen`.

### Auto-refresh: one-shot timer
Uses `set_timer` (not `set_interval`) so the countdown starts after the API call finishes, not before.

### TTL cache pattern
`Users`/`Teams` use a two-method pattern: the public method calls `ttl_hash()` at invocation time and passes it to an `@lru_cache` private method. Do NOT use `ttl_hash()` as a default argument — default args are evaluated once at import time, so the cache would never expire.

### Cursor visibility gates actions
`DataTable` is initialised with `show_cursor=False`. The cursor becomes visible only on explicit user intent: navigation keys (`up`/`down`/`pageup`/`pagedown`) or a click on a row. All cursor-based actions (`action_inspect`, `action_toggle_select`, `action_open_url`, `_resolve_targets`) guard on `table.show_cursor`, not `bool(_incident_ids)`. After a reload, if the previously pointed incident is no longer in the list `show_cursor` is reset to `False`. Tests that exercise cursor-based actions must set `table.show_cursor = True` explicitly.

### on_unmount
Children are already removed in `on_unmount` — `query_one` raises `NoMatches`. Track mutable state as screen fields updated via event handlers; `on_unmount` only calls `self.app.save_prefs()`.

## Dependencies

- `pagerduty` 6.x switched from requests to httpx — `response.ok` is gone, use `response.is_success`.
- Textual 8.x, `rich>=14.2.0`. `StatusBar` buttons are plain `Button()` with no `compact`/`flat`/`variant` kwargs — styled via TCSS only.
