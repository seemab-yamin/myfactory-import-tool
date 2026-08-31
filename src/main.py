import sys

from src.cli import create_parser
from src.logger import get_logger
from src.web_ui import launch_web_ui

logger = get_logger(__name__)

# ========== Main Entrypoint ==========


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
