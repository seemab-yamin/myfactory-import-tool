import sys
from pathlib import Path

APP_NAME = "MyFactoryImportTool"
DEFAULT_PROJECT_DIR = Path.home() / "Documents" / APP_NAME


def get_project_dir() -> Path:
    """
    Ask the user whether they want to use the default project directory
    or provide a custom directory.

    The application terminates if a custom path is provided but cannot
    be created or accessed.
    """
    print()
    print("MyFactory Import Tool")
    print("-" * 50)
    print("Default project directory:")
    print(f"  {DEFAULT_PROJECT_DIR}")
    print()

    choice = (
        input("Do you want to change the project directory? [y/N]: ").strip().lower()
    )

    # User chose the default directory.
    if choice in ("", "n", "no"):
        project_dir = DEFAULT_PROJECT_DIR

    # User wants to provide a custom directory.
    elif choice in ("y", "yes"):
        custom_path = input("Enter the new project directory: ").strip()

        if not custom_path:
            print("ERROR: No project directory was provided.")
            sys.exit(1)

        project_dir = Path(custom_path)

    else:
        print(f"ERROR: Invalid choice '{choice}'. " "Please enter 'y' or 'n'.")
        sys.exit(1)

    # Validate/create the selected project directory.
    try:
        project_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Verify that the directory is actually accessible.
        if not project_dir.is_dir():
            raise OSError(f"Path exists but is not a directory: {project_dir}")

    except (OSError, ValueError) as exc:
        print()
        print(
            f"ERROR: Unable to access project directory:\n"
            f"  {project_dir}\n"
            f"Reason: {exc}"
        )
        sys.exit(1)

    print()
    print("Using project directory:")
    print(f"  {project_dir}")

    return project_dir


PROJECT_DIR = get_project_dir()

DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
