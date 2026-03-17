# PDH New Generation

A PagerDuty terminal UI for humans. Manage incidents interactively without leaving the terminal.

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

`pdh-ng` requires three values to talk to the PagerDuty API:

| Key | Description |
|-----|-------------|
| `apikey` | API key — generate from your PagerDuty profile page |
| `email` | Email address of your PagerDuty account |
| `uid` | Your PagerDuty user ID — visible in the URL when viewing your profile |

### Config file

Create `~/.config/pdh-ng/config.yaml`:

```yaml
apikey: your-api-key
email: you@example.com
uid: UXXXXXXX
```

### Environment variables

Alternatively, or to override specific keys:

```sh
export PDH_NG_APIKEY=your-api-key
export PDH_NG_UID=UXXXXXXX
export PDH_NG_EMAIL=you@example.com
```

Environment variables fill in any keys missing from the config file. The file takes precedence over env vars.

## Usage

```sh
pdh-ng
```

### Keybindings

| Key | Action |
|-----|--------|
| `1` | Cycle scope: mine → team → all |
| `2` | Cycle status filter: all → triggered → acknowledged |
| `a` | Acknowledge selected incident(s) |
| `r` | Resolve selected incident(s) |
| `s` | Snooze selected incident(s) |
| `space` | Select/deselect incident |
| `f` | Toggle title filter |
| `c` | Select visible columns |
| `enter` | Open incident detail |
| `ctrl+r` | Reload |
| `q` | Quit |

## UI preferences

Column visibility is persisted to `~/.local/state/pdh-ng/ui.yaml`.
