import argparse
import os
import sys

from rich import print

from .config import load_and_validate
from .tui import TuiApp


def main():
    parser = argparse.ArgumentParser(
        prog="pdh-ng",
        description="PDH New Generation.",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="FILE",
        help="path to config file (default: ~/.config/pdh-ng/config.yaml)",
    )
    args = parser.parse_args()

    config_path = args.config or os.environ.get("PDH_NG_CONFIG", "~/.config/pdh-ng/config.yaml")

    if args.config and not os.path.isfile(os.path.expanduser(args.config)):
        print(f"[red]Config file not found: {args.config}[/red]")
        sys.exit(1)

    cfg = load_and_validate(config_path)
    TuiApp(cfg=cfg).run()
