import os

from .config import load_and_validate
from .tui import TuiApp


def main():
    config_path = os.environ.get("PDH_NG_CONFIG", "~/.config/pdh-ng/config.yaml")
    cfg = load_and_validate(config_path)
    TuiApp(cfg=cfg).run()
