from pathlib import Path

import pandas as pd

from config_manager import ConfigManager
from logger import setup_logger
from mapper import FieldMapper
from models import ImportResult, ImportStatus

logger = setup_logger(__name__)


class MyfactoryImporter:
    """Main importer class for Myfactory CRM"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.delimiter = config.get("import.default_delimiter", ",")
        self.batch_size = config.get("import.batch_size", 100)
        self.skip_header = config.get("import.skip_header", True)

    def import_file(
        self, file_path: str, mapping_name: str = "default", dry_run: bool = False
    ) -> ImportResult:
        """Main import method"""

        logger.info(f"Starting import from: {file_path}")
        logger.info(f"Using mapping: {mapping_name}")
        logger.info(f"Dry run: {dry_run}")

        try:
            # 1. Read CSV
            df = self._read_csv(file_path)
            logger.info(f"Read {len(df)} rows from CSV")

            if dry_run:
                logger.info("*** DRY RUN MODE - No changes will be made ***")

            # 2. Get mapping
            mapping = self.config.get_mapping(mapping_name)
            if not mapping:
                raise ValueError(f"Mapping '{mapping_name}' not found")

            # 3. Map fields
            mapper = FieldMapper(mapping)
            mapped_df = mapper.map_dataframe(df)

            # 4. Validate data
            errors = self._validate_data(mapped_df)

            if errors:
                logger.error(f"Validation found {len(errors)} errors")
                for error in errors[:10]:  # Show first 10 errors
                    logger.error(f"  - {error}")

            # 5. Dry run - only preview
            if dry_run:
                logger.info("=== DRY RUN PREVIEW ===")
                logger.info(f"Rows to import: {len(mapped_df)}")
                logger.info(f"Columns: {list(mapped_df.columns)}")
                preview_rows = min(5, len(mapped_df))
                logger.info(f"\nFirst {preview_rows} rows:")
                print(mapped_df.head(preview_rows).to_string())

                return ImportResult(
                    status=ImportStatus.DRY_RUN,
                    total_rows=len(df),
                    imported_rows=0,
                    failed_rows=0,
                    errors=errors,
                    log_file=logger.handlers[0].baseFilename if logger.handlers else "",
                )

            # 6. Actual import - save to database (placeholder)
            imported_count = self._import_to_database(mapped_df)

            # 7. Log results
            logger.info(f"✓ Import completed: {imported_count} rows imported")

            return ImportResult(
                status=ImportStatus.SUCCESS,
                total_rows=len(df),
                imported_rows=imported_count,
                failed_rows=len(df) - imported_count,
                errors=errors,
                log_file=logger.handlers[0].baseFilename if logger.handlers else "",
            )

        except Exception as e:
            logger.error(f"Import failed: {str(e)}", exc_info=True)
            return ImportResult(
                status=ImportStatus.FAILED,
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                errors=[str(e)],
                log_file=logger.handlers[0].baseFilename if logger.handlers else "",
            )

    def _read_csv(self, file_path: str) -> pd.DataFrame:
        """Read CSV file with proper encoding and delimiter detection"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Auto-detect delimiter
            with open(file_path, "r", encoding="utf-8") as f:
                first_line = f.readline()

            # Detect delimiter
            if "\t" in first_line:
                delimiter = "\t"
            elif ";" in first_line:
                delimiter = ";"
            else:
                delimiter = self.delimiter

            # Read CSV
            df = pd.read_csv(
                file_path, delimiter=delimiter, encoding="utf-8", skip_blank_lines=True
            )

            if self.skip_header:
                # First row is header (already handled by pandas)
                pass

            logger.info(f"Read {len(df)} rows, {len(df.columns)} columns")
            logger.info(f"Detected delimiter: {delimiter}")
            logger.info(f"Columns: {list(df.columns)}")

            return df

        except UnicodeDecodeError:
            # Try other encodings
            for encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                try:
                    df = pd.read_csv(
                        file_path, delimiter=self.delimiter, encoding=encoding
                    )
                    logger.info(f"Successfully read with encoding: {encoding}")
                    return df
                except:
                    continue

            raise ValueError("Unable to read CSV with any encoding")

    def _validate_data(self, df: pd.DataFrame) -> list:
        """Validate DataFrame before import"""
        errors = []

        # Check for required columns
        required_cols = ["ArticleCode", "Description", "Price"]
        for col in required_cols:
            if col not in df.columns:
                errors.append(f"Required column '{col}' not found")

        # Check for empty values
        if not df.empty:
            for col in df.columns:
                null_count = df[col].isnull().sum()
                if null_count > 0:
                    errors.append(f"Column '{col}' has {null_count} null values")
        return errors

    def _import_to_database(self, df: pd.DataFrame) -> int:
        """Import mapped data to Myfactory database"""
        # Placeholder - implement actual DB connection
        logger.info("Database import placeholder - implement connection")

        # Check database config
        db_config = self.config.get_database_config()
        logger.info(f"Database config: {db_config['server']} - {db_config['database']}")

        # For now, just return row count
        return len(df)
