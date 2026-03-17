import json
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
    cfg = {}

    def __init__(self) -> None:
        super().__init__()
        self.cfg = {}

    def from_yaml(self, path, key: str | None = None) -> None:
        """Load configuration from a yaml file, store it directly or under the specified key."""

        with open(os.path.expanduser(path)) as f:
            o = yaml.safe_load(f.read())
        if key:
            self.cfg[key] = o
        else:
            self.cfg.update(o)

    def from_dict(self, d: dict) -> None:
        self.cfg.update(d)

    def to_dict(self) -> dict:
        return self.cfg.copy()

    def to_yaml(self, fileName: str) -> None:
        with open(os.path.expanduser(fileName), "w") as f:
            yaml.safe_dump(self.cfg, f)

    def to_json(self, fileName: str) -> None:
        with open(os.path.expanduser(fileName), "w") as f:
            json.dump(self.cfg, f)

    def from_json(self, path, key: str | None = None) -> None:
        """Load configuration from a json file, store it directly or under the specified key."""
        with open(os.path.expanduser(path)) as f:
            o = json.load(f)

        if key:
            self.cfg[key] = o
        else:
            self.cfg.update(o)

    def validate(self) -> bool:
        for k in REQUIRED_KEYS:
            if k not in self.cfg.keys():
                return False
        return True

    def __getitem__(self, key: str) -> Any:
        return self.cfg[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.cfg[key] = value

    def __repr__(self) -> str:
        return repr(self.cfg)

    def __str__(self) -> str:
        return repr(self.cfg)

    def get(self, key: str, default=None):
        return self.cfg.get(key, default)

    def __contains__(self, key) -> bool:
        return key in self.cfg


config = Config()


ENV_KEYS = {
    "apikey": "PDH_NG_APIKEY",
    "uid": "PDH_NG_UID",
    "email": "PDH_NG_EMAIL",
}


def load_and_validate(fileName: str) -> Config:
    try:
        config.from_yaml(fileName)
    except FileNotFoundError:
        pass

    for key, env_var in ENV_KEYS.items():
        if key not in config and (val := os.environ.get(env_var)):
            config[key] = val

    missing = [ENV_KEYS[k] for k in REQUIRED_KEYS if k not in config]
    if missing:
        vars = ", ".join(missing)
        print(f"[red]Missing config. Set via ~/.config/pdh-ng/config.yaml or env: {vars}[/red]")
        sys.exit(1)

    for key, value in DEFAULTS.items():
        if key not in config:
            config[key] = value

    return config
