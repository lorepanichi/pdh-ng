from __future__ import annotations

import logging
from pathlib import Path

import yaml
from textual.app import App

from ..config import Config
from .screens import IncidentsScreen
from .widgets import ALL_COLUMNS, DEFAULT_COLUMNS

logger = logging.getLogger("pdh-ng.tui")

_PREFS_PATH = Path("~/.local/state/pdh-ng/ui.yaml")


class TuiApp(App):
    TITLE = "PDH New Generation"
    CSS_PATH = "styles.tcss"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, cfg: Config, show_all: bool = False) -> None:
        super().__init__()
        self.cfg = cfg
        self.show_all = show_all
        self._prefs_path = _PREFS_PATH.expanduser()
        self._prefs: dict = self._load_prefs()
        self._setup_logging()

    def _setup_logging(self) -> None:
        if not self.cfg.get("log_enabled", True):
            logging.getLogger("pdh-ng").addHandler(logging.NullHandler())
            return
        log_file = Path(self.cfg.get("log_file", "~/.local/state/pdh-ng/logs/tui.log")).expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_file),
            level=getattr(logging, self.cfg.get("log_level", "DEBUG").upper(), logging.DEBUG),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

    def _load_prefs(self) -> dict:
        try:
            if self._prefs_path.exists():
                with open(self._prefs_path) as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Could not load UI prefs: %s", e)
        return {}

    def save_prefs(self) -> None:
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._prefs_path, "w") as f:
                yaml.dump(self._prefs, f)
        except Exception as e:
            logger.warning("Could not save UI prefs: %s", e)

    @property
    def visible_columns(self) -> list[str]:
        cols = self._prefs.get("columns", list(DEFAULT_COLUMNS))
        return [c for c in cols if c in ALL_COLUMNS]

    @visible_columns.setter
    def visible_columns(self, columns: list[str]) -> None:
        self._prefs["columns"] = columns
        self.save_prefs()

    @property
    def refresh_interval(self) -> int:
        return self._prefs.get("refresh_interval", 5)

    @refresh_interval.setter
    def refresh_interval(self, interval: int) -> None:
        self._prefs["refresh_interval"] = interval
        self.save_prefs()

    @property
    def scope(self) -> str:
        return self._prefs.get("scope", "mine")

    @property
    def status_mode(self) -> str:
        return self._prefs.get("status_mode", "all")

    def on_mount(self) -> None:
        self.push_screen(IncidentsScreen(show_all=self.show_all))
