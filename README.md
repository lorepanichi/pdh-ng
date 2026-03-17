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

```sh
pdh-ng
```

### Keybindings

| Key | Action |
|-----|--------|
| `1` | Cycle scope: mine → team → all |
| `2` | Cycle status filter: all → triggered → acknowledged |
| `3` | Cycle refresh time: 5s → 10s → off → 3s |
| `a` | Acknowledge selected incident(s) |
| `r` | Resolve selected incident(s) |
| `s` | Snooze selected incident(s) |
| `space` | Select/deselect incident |
| `escape` | Clear incidents selection |
| `f` | Toggle title filter (prefix with `!` to exclude) |
| `c` | Select visible columns |
| `q` | Quit |

## UI preferences

Column visibility is persisted to `~/.local/state/pdh-ng/ui.yaml`.
