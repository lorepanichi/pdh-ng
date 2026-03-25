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

logger = logging.getLogger("pdh-ng")

if platform.system() == "Darwin":
    _PREFS_PATH = Path("~/Library/Application Support/pdh-ng/ui.yaml")
else:
    _PREFS_PATH = Path("~/.local/state/pdh-ng/ui.yaml")


class TuiApp(App):
    """Textual application root — holds config, the shared PagerDuty client, and UI preferences."""

    TITLE = "PDH New Generation"
    CSS_PATH = "styles.tcss"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, cfg: Config) -> None:
        """Initialise the app, create the shared PagerDuty client, and load prefs.

        Args:
            cfg: Loaded and validated application config.
        """
        super().__init__()
        self.cfg = cfg
        self.pd = PagerDuty(cfg)
        self._prefs_path = _PREFS_PATH.expanduser()
        self._prefs: dict = self._load_prefs()
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure file-based logging from config, or add a NullHandler if disabled."""
        if not self.cfg["log_enabled"]:
            logging.getLogger("pdh-ng").addHandler(logging.NullHandler())
            return
        log_file = Path(self.cfg["log_file"]).expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_level = getattr(logging, self.cfg["log_level"].upper())
        logging.basicConfig(
            filename=str(log_file),
            level=log_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        if log_level > logging.DEBUG:
            logging.getLogger("httpx").setLevel(logging.WARNING)

    def _load_prefs(self) -> dict:
        """Load UI preferences from the YAML prefs file.

        Returns:
            Parsed prefs dict, or an empty dict if the file is missing or unreadable.
        """
        try:
            if self._prefs_path.exists():
                with open(self._prefs_path) as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Could not load UI prefs: %s", e)
        return {}

    def save_prefs(self) -> None:
        """Persist the in-memory prefs dict to the YAML prefs file."""
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._prefs_path, "w") as f:
                yaml.dump(self._prefs, f)
        except Exception as e:
            logger.warning("Could not save UI prefs: %s", e)

    @property
    def visible_columns(self) -> list[str]:
        """Visible column list, filtered to known columns. Defaults to all columns."""
        cols = self._prefs.get("visible_columns", list(ALL_COLUMNS))
        return [c for c in cols if c in ALL_COLUMNS]

    @visible_columns.setter
    def visible_columns(self, columns: list[str]) -> None:
        self._prefs["visible_columns"] = columns

    @property
    def refresh_time(self) -> RefreshTime:
        """Auto-refresh interval, defaulting to 5s."""
        return RefreshTime(self._prefs.get("refresh_time", RefreshTime.S5))

    @refresh_time.setter
    def refresh_time(self, value: RefreshTime) -> None:
        self._prefs["refresh_time"] = int(value)

    @property
    def inc_scope(self) -> IncScope:
        """Incident scope filter, defaulting to mine."""
        return IncScope(self._prefs.get("inc_scope", IncScope.MINE))

    @inc_scope.setter
    def inc_scope(self, value: IncScope) -> None:
        self._prefs["inc_scope"] = int(value)

    @property
    def inc_status(self) -> IncStatus:
        """Incident status filter, defaulting to all."""
        return IncStatus(self._prefs.get("inc_status", IncStatus.ALL))

    @inc_status.setter
    def inc_status(self, value: IncStatus) -> None:
        self._prefs["inc_status"] = int(value)

    @property
    def inc_urgency(self) -> IncUrgency:
        """Incident urgency filter, defaulting to all."""
        return IncUrgency(self._prefs.get("inc_urgency", IncUrgency.ALL))

    @inc_urgency.setter
    def inc_urgency(self, value: IncUrgency) -> None:
        self._prefs["inc_urgency"] = int(value)

    @property
    def auto_ack(self) -> bool:
        """Whether auto-ack is enabled, defaulting to False."""
        return self._prefs.get("auto_ack", False)

    @auto_ack.setter
    def auto_ack(self, value: bool) -> None:
        self._prefs["auto_ack"] = value

    def on_mount(self) -> None:
        """Push the incidents screen with all persisted UI preferences."""
        self.push_screen(
            IncidentsScreen(
                inc_scope=self.inc_scope,
                inc_status=self.inc_status,
                inc_urgency=self.inc_urgency,
                refresh_time=self.refresh_time,
                auto_ack=self.auto_ack,
                visible_columns=self.visible_columns,
            )
        )
