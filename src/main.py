#!/usr/bin/env python3
"""
Myfactory Import Tool - CLI Entry Point

Usage:
    python src/main.py --file sample.csv --mapping default --dry-run
    python src/main.py --file sample.csv --mapping custom
    python src/main.py --file sample.csv --validate-config
"""

import argparse
import sys
from pathlib import Path
from src.config_manager import ConfigManager
from src.importer import MyfactoryImporter
from src.logger import setup_logger
from src.models import ImportStatus


def main():
    """Main CLI entry point"""

    # Setup parser
    parser = argparse.ArgumentParser(
        description="Myfactory Article Import Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file data.csv --mapping default
  %(prog)s --file data.csv --dry-run
  %(prog)s --file data.csv --mapping custom --batch 50
  %(prog)s --validate-config
        """,
    )

    parser.add_argument("--file", "-f", type=str, help="Path to CSV file to import")

    parser.add_argument(
        "--mapping",
        "-m",
        type=str,
        default="default",
        help="Mapping configuration to use (default: default)",
    )

    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Preview import without making changes",
    )

    parser.add_argument(
        "--batch",
        "-b",
        type=int,
        default=100,
        help="Batch size for import (default: 100)",
    )

    parser.add_argument(
        "--validate-config", action="store_true", help="Validate configuration and exit"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    # Parse arguments
    args = parser.parse_args()

    # Setup logger
    logger = setup_logger("myfactory_import")

    # Validate config mode
    if args.validate_config:
        print("Validating configuration...")
        config = ConfigManager()
        print(f"✓ Config loaded: {Path('config/config.json').absolute()}")
        print(f"✓ Mapping names: {list(config.get('mappings', {}).keys())}")
        db_config = config.get_database_config()
        print(f"✓ Database: {db_config['server']} - {db_config['database']}")
        print("✓ Configuration valid!")
        sys.exit(0)

    # Check if file provided
    if not args.file:
        parser.print_help()
        print("\nError: --file is required")
        sys.exit(1)

    # Check if file exists
    if not Path(args.file).exists():
        logger.error(f"File not found: {args.file}")
        sys.exit(1)

    # Initialize config and importer
    config = ConfigManager()
    importer = MyfactoryImporter(config)

    # Set batch size from args
    importer.batch_size = args.batch

    # Run import
    result = importer.import_file(
        file_path=args.file, mapping_name=args.mapping, dry_run=args.dry_run
    )

    # Print summary
    print("\n" + "=" * 50)
    print("IMPORT SUMMARY")
    print("=" * 50)
    print(f"Status: {result.status.value}")
    print(f"Total Rows: {result.total_rows}")
    print(f"Imported: {result.imported_rows}")
    print(f"Failed: {result.failed_rows}")
    print(f"Log file: {result.log_file}")

    if result.errors:
        print(f"Errors: {len(result.errors)}")
        for error in result.errors[:5]:
            print(f"  - {error}")

    print("=" * 50)

    # Return exit code
    if result.status == ImportStatus.SUCCESS:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
