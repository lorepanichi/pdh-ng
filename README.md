# PDH New Generation

A PagerDuty terminal UI built with [Textual](https://github.com/Textualize/textual). Manage incidents interactively without leaving the terminal.

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

## Install

### With pipx

```sh
pipx install git+https://github.com/lorepanichi/pdh-ng
```

### From source

```sh
git clone https://github.com/lorepanichi/pdh-ng
cd pdh-ng
uv sync
uv tool install .
```

## Configuration

Config file: `~/.config/pdh-ng/config.yaml` (override with `-c FILE` or `PDH_NG_CONFIG`).

Every key can be set in the config file or via its environment variable (`PDH_NG_<KEY_UPPERCASE>`). The file takes precedence over env vars.

### Required

| Key | Env var | Description |
|-----|---------|-------------|
| `apikey` | `PDH_NG_APIKEY` | API key — generate from your PagerDuty profile page |
| `email` | `PDH_NG_EMAIL` | Email address of your PagerDuty account |
| `uid` | `PDH_NG_UID` | Your PagerDuty user ID — visible in the URL when viewing your profile |

### Optional

| Key | Env var | Default | Description |
|-----|---------|---------|-------------|
| `log_enabled` | `PDH_NG_LOG_ENABLED` | `true` | Enable/disable logging |
| `log_file` | `PDH_NG_LOG_FILE` | `~/.local/state/pdh-ng/logs/tui.log` | Log file path |
| `log_level` | `PDH_NG_LOG_LEVEL` | `DEBUG` | Log level |
| `max_network_attempts` | `PDH_NG_MAX_NETWORK_ATTEMPTS` | `5` | Retry attempts for API calls |

### Example config file

```yaml
apikey: your-api-key
email: you@example.com
uid: UXXXXXXX
```

## Usage

```
pdh-ng [-c FILE] [-d]
```

**Options**

| Flag | Description |
|------|-------------|
| `-V`, `--version` | Print version and exit. |
| `-c FILE`, `--config FILE` | Use FILE as config. Exits with error if FILE does not exist. Overrides `PDH_NG_CONFIG`. |
| `-d`, `--debug` | Force log level to DEBUG, overriding the config value. |

### Keybindings

**Status bar (filters & controls)**

| Key | Action |
|-----|--------|
| `1` | Cycle scope: mine → team → all |
| `2` | Cycle status filter: all → triggered → acknowledged |
| `3` | Cycle urgency filter: all → high → low |
| `4` | Toggle auto-ack on/off |
| `5` | Cycle auto-refresh interval: off → 3s → 5s → 10s |

**Incident actions**

| Key | Action |
|-----|--------|
| `i` | Open incident detail |
| `y` | Copy incident title to clipboard |
| `o` | Open incident URL in browser |
| `a` | Acknowledge selected incident(s) |
| `r` | Resolve selected incident(s) |
| `s` | Snooze selected incident(s) |
| `space` | Select / deselect incident |
| `escape` | Clear selection, or hide title filter |

**View**

| Key | Action |
|-----|--------|
| `f` | Toggle title filter input (prefix term with `!` to exclude) |
| `c` | Select visible columns |

**Other**
| Key | Action |
|-----|--------|
| `q` | Quit |

### Auto-ack

When auto-ack is on (`4`), every table load silently acknowledges all **triggered** incidents assigned to you - regardless of the active scope. Other users' incidents are never touched. Auto-acked rows show a `!` marker for one refresh cycle; a toast notification reports how many were acked.

## UI preferences

Scope, status filter, urgency filter, auto-ack, refresh interval, and column visibility are all persisted to `~/.local/state/pdh-ng/ui.yaml` and restored on next launch.

Changing the refresh interval resets the auto-refresh timer — the next fetch starts a full interval from that moment.

Changing visible columns re-renders already-fetched data from memory — no API call, no timer reset.
