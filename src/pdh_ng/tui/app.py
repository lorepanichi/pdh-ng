from __future__ import annotations

import logging
import platform
from pathlib import Path

import yaml
from textual.app import App

from ..config import Config
from ..pd import PagerDuty
from .constants import ALL_COLUMNS, IncScope, IncStatus, IncUrgency, RefreshTime
from .screens import IncidentsScreen

logger = logging.getLogger("pdh-ng.tui")

if platform.system() == "Darwin":
    _PREFS_PATH = Path("~/Library/Application Support/pdh-ng/ui.yaml")
else:
    _PREFS_PATH = Path("~/.local/state/pdh-ng/ui.yaml")


class TuiApp(App):
    TITLE = "PDH New Generation"
    CSS_PATH = "styles.tcss"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.pd = PagerDuty(cfg)
        self._prefs_path = _PREFS_PATH.expanduser()
        self._prefs: dict = self._load_prefs()
        self._setup_logging()

    def _setup_logging(self) -> None:
        if not self.cfg["log_enabled"]:
            logging.getLogger("pdh-ng").addHandler(logging.NullHandler())
            return
        log_file = Path(self.cfg["log_file"]).expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_file),
            level=getattr(logging, self.cfg["log_level"].upper()),
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
        cols = self._prefs.get("visible_columns", list(ALL_COLUMNS))
        return [c for c in cols if c in ALL_COLUMNS]

    @visible_columns.setter
    def visible_columns(self, columns: list[str]) -> None:
        self._prefs["visible_columns"] = columns

    @property
    def refresh_time(self) -> RefreshTime:
        return RefreshTime(self._prefs.get("refresh_time", RefreshTime.S5))

    @refresh_time.setter
    def refresh_time(self, value: RefreshTime) -> None:
        self._prefs["refresh_time"] = int(value)

    @property
    def inc_scope(self) -> IncScope:
        return IncScope(self._prefs.get("inc_scope", IncScope.MINE))

    @inc_scope.setter
    def inc_scope(self, value: IncScope) -> None:
        self._prefs["inc_scope"] = int(value)

    @property
    def inc_status(self) -> IncStatus:
        return IncStatus(self._prefs.get("inc_status", IncStatus.ALL))

    @inc_status.setter
    def inc_status(self, value: IncStatus) -> None:
        self._prefs["inc_status"] = int(value)

    @property
    def inc_urgency(self) -> IncUrgency:
        return IncUrgency(self._prefs.get("inc_urgency", IncUrgency.ALL))

    @inc_urgency.setter
    def inc_urgency(self, value: IncUrgency) -> None:
        self._prefs["inc_urgency"] = int(value)

    def on_mount(self) -> None:
        self.push_screen(IncidentsScreen())
