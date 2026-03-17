import os
import sys
from typing import Any

import yaml
from rich import print

REQUIRED_KEYS = ["apikey", "uid", "email"]

DEFAULTS = {
    "log_enabled": True,
    "log_file": "~/.local/state/pdh-ng/logs/tui.log",
    "log_level": "DEBUG",
    "max_network_attempts": 5,
}


class Config:
    def __init__(self) -> None:
        self.cfg: dict = {}

    def from_yaml(self, path: str) -> None:
        with open(os.path.expanduser(path)) as f:
            o = yaml.safe_load(f.read())
        self.cfg.update(o)

    def __getitem__(self, key: str) -> Any:
        return self.cfg[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.cfg[key] = value

    def __repr__(self) -> str:
        return repr(self.cfg)

    def get(self, key: str, default=None):
        return self.cfg.get(key, default)

    def __contains__(self, key) -> bool:
        return key in self.cfg


config = Config()


def _env_var(key: str) -> str:
    return f"PDH_NG_{key.upper()}"


def load_and_validate(fileName: str) -> Config:
    try:
        config.from_yaml(fileName)
    except FileNotFoundError:
        pass
    except (yaml.YAMLError, ValueError):
        print("[red]Config file must be valid YAML with a mapping at the root.[/red]")
        sys.exit(1)

    for key in REQUIRED_KEYS + list(DEFAULTS.keys()):
        if key not in config and (val := os.environ.get(_env_var(key))):
            config[key] = val

    missing_keys = [k for k in REQUIRED_KEYS if k not in config]
    if missing_keys:
        missing_env = [_env_var(k) for k in missing_keys]
        print(
            f"[red]Missing required config: {', '.join(missing_keys)}."
            f" Set via config file or env: {', '.join(missing_env)}[/red]"
        )
        sys.exit(1)

    for key, value in DEFAULTS.items():
        if key not in config:
            config[key] = value

    return config
