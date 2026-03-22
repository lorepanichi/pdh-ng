import argparse
import importlib.metadata
import os
import platform
import sys

from rich import print

from .config import load_and_validate
from .tui import TuiApp

_DEFAULT_CONFIG = (
    "~/Library/Application Support/pdh-ng/config.yaml"
    if platform.system() == "Darwin"
    else "~/.config/pdh-ng/config.yaml"
)


def main():
    parser = argparse.ArgumentParser(
        prog="pdh-ng",
        description="PDH New Generation.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {importlib.metadata.version('pdh-ng')}",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="FILE",
        help=f"path to config file (default: {_DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="enable debug logging",
    )
    args = parser.parse_args()

    config_path = args.config or os.environ.get("PDH_NG_CONFIG", _DEFAULT_CONFIG)

    if args.config and not os.path.isfile(os.path.expanduser(args.config)):
        print(f"[red]Config file not found: {args.config}[/red]")
        sys.exit(1)

    cfg = load_and_validate(config_path)
    if args.debug:
        cfg["log_level"] = "DEBUG"
    TuiApp(cfg=cfg).run()
