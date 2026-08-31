#!/usr/bin/env python3
"""Main entry point for MyFactory Import Tool."""

import sys

from src.cli import create_parser
from src.logger import get_logger
from src.web.ui_launcher import launch_web_ui

logger = get_logger(__name__)


def main():
    """Main entrypoint for CLI."""
    # If no arguments, launch Web UI
    if len(sys.argv) == 1:
        launch_web_ui()
        return
    parser = create_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
