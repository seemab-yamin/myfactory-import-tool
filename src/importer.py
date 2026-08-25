"""Core import logic for Myfactory with CSV/Excel parsing, batch insert, and audit logging."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from sqlalchemy import text

from src.config_manager import get_config_manager
from src.db import get_db_manager, local_session, myfactory_session
from src.logger import get_logger
from src.mapper import get_mapper
from src.models import (
    ImportAudit,
    ImportConfigDTO,
    ImportResultDTO,
    ImportStatus,
    get_table_name,
)

logger = get_logger(__name__)


class MyfactoryImporter:
    """
    Main importer class for Myfactory CRM.

    Handles:
        - CSV/Excel parsing with auto-delimiter detection
        - Column mapping via FieldMapper
        - Batch insert with error tolerance
        - Dry-run mode with preview
        - Audit logging
    """

    def __init__(
        self,
        batch_size: int = 1000,
        table_name: str = None,
        auto_fetch_mapping: bool = True,
    ):
        """
        Initialize the importer.

        Args:
            batch_size: Number of rows per batch
            table_name: Target table name (default from config)
        """
        self.auto_fetch_mapping = auto_fetch_mapping
        self.batch_size = batch_size or get_config_manager().get().default_batch_size
        self.table_name = table_name or get_table_name()
        self.mapper = get_mapper()
        self.db_manager = get_db_manager()
        self._target_columns = None

    def get_target_columns(self) -> List[str]:
        """Get target columns from the database."""
        if self._target_columns is None:
            columns = self.db_manager.get_table_columns(self.table_name, use_cache=True)
            self._target_columns = [col["name"] for col in columns]
        return self._target_columns

    def import_file(
        self, config: Union[ImportConfigDTO, Dict[str, Any]]
    ) -> ImportResultDTO:
        """
        Import a file with the given configuration.

        Args:
            config: ImportConfigDTO or dict with file_path, supplier_name, etc.

        Returns:
            ImportResultDTO with import summary
        """
        # Convert dict to DTO if needed
        if isinstance(config, dict):
            config = ImportConfigDTO(**config)

        logger.info("=" * 60)
        logger.info(f"🚀 Starting import from: {config.file_path}")
        logger.info(f"   Supplier: {config.supplier_name}")
        logger.info(f"   Table: {config.table_name}")
        logger.info(f"   Dry run: {config.dry_run}")
        logger.info(f"   Batch size: {config.batch_size}")
        logger.info("=" * 60)

        # Create audit record
        audit = ImportAudit.create_from_import(
            supplier_name=config.supplier_name,
            file_path=config.file_path,
            table_name=config.table_name,
            dry_run=config.dry_run,
        )

        # Save audit record
        with local_session() as session:
            session.add(audit)
            session.flush()
            audit_id = audit.id

        try:
            # 1. Read file
            df = self._read_file(config.file_path, config.delimiter)

            # 2. Get mapping
            if config.mapping:
                # Use provided mapping
                mapping = config.mapping
            else:
                # Load from database
                mapping = self.mapper.get_mappings(
                    config.supplier_name, active_only=True
                )
            if not mapping:
                raise ValueError(
                    f"No mapping found for supplier '{config.supplier_name}'. "
                    "Please configure mappings first."
                )

            # 3. Apply mapping
            mapped_df = self._apply_mapping(df, mapping)

            # 4. Validate against target schema
            validated_df, errors = self._validate_schema(mapped_df)

            # 5. Dry run or actual import
            if config.dry_run:
                result = self._dry_run(validated_df, mapping, audit_id)
            else:
                result = self._perform_import(validated_df, audit_id, config.batch_size)

            # 6. Update audit
            result.audit_id = audit_id
            self._update_audit(audit_id, result, errors)

            # 7. Log summary
            self._log_summary(result, config.dry_run)

            return result

        except Exception as e:
            logger.error(f"❌ Import failed: {e}", exc_info=True)

            # Update audit with failure
            with local_session() as session:
                audit = (
                    session.query(ImportAudit)
                    .filter(ImportAudit.id == audit_id)
                    .first()
                )
                if audit:
                    audit.status = ImportStatus.FAILED.value
                    audit.error_message = str(e)
                    audit.completed_at = datetime.utcnow()
                    session.commit()

            return ImportResultDTO(
                status=ImportStatus.FAILED,
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                skipped_rows=0,
                errors=[str(e)],
                log_file=logger.handlers[0].baseFilename if logger.handlers else "",
                audit_id=audit_id,
            )

    def _read_file(
        self, file_path: str, delimiter: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Read CSV or Excel file with auto-delimiter detection.

        Args:
            file_path: Path to file
            delimiter: Optional delimiter override

        Returns:
            DataFrame with file contents
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()

        try:
            if ext in [".csv"]:
                df = self._read_csv(path, delimiter)
            elif ext in [".xlsx", ".xls"]:
                df = self._read_excel(path)
            else:
                raise ValueError(
                    f"Unsupported file type: {ext}. Please use CSV or Excel."
                )

            if df.empty:
                logger.warning("File is empty")

            logger.info(f"✅ Read {len(df)} rows, {len(df.columns)} columns")
            logger.info(f"   Columns: {list(df.columns)}")

            return df

        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            raise

    def _read_csv(self, path: Path, delimiter: Optional[str] = None) -> pd.DataFrame:
        """Read CSV with auto-delimiter detection."""
        # Auto-detect delimiter
        if delimiter is None:
            with open(path, "r", encoding="utf-8-sig") as f:
                first_line = f.readline()

            # Check for common delimiters
            if "\t" in first_line:
                delimiter = "\t"
            elif ";" in first_line:
                delimiter = ";"
            else:
                delimiter = ","

            logger.info(f"Detected delimiter: '{delimiter}'")

        # Try different encodings
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        for encoding in encodings:
            try:
                df = pd.read_csv(
                    path,
                    delimiter=delimiter,
                    encoding=encoding,
                    skip_blank_lines=True,
                    dtype=str,
                    keep_default_na=False,
                )
                logger.info(f"Read CSV with encoding: {encoding}")
                return df
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.debug(f"Failed with encoding {encoding}: {e}")
                continue

        raise ValueError("Could not read CSV with any encoding")

    def _read_excel(self, path: Path) -> pd.DataFrame:
        """Read Excel file."""
        try:
            # Try reading all sheets and merging
            xl = pd.ExcelFile(path)

            if len(xl.sheet_names) > 1:
                logger.info(f"Found {len(xl.sheet_names)} sheets, merging all")
                dfs = []
                for sheet in xl.sheet_names:
                    df = pd.read_excel(
                        path, sheet_name=sheet, dtype=str, keep_default_na=False
                    )
                    dfs.append(df)
                df = pd.concat(dfs, ignore_index=True)
            else:
                df = pd.read_excel(path, dtype=str, keep_default_na=False)

            logger.info(f"Read Excel with {len(xl.sheet_names)} sheets")
            return df

        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {e}")

    def _apply_mapping(self, df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
        """Apply field mapping to DataFrame."""
        # Keep only mapped columns
        mapped_data = {}
        for source_field, target_field in mapping.items():
            if source_field in df.columns:
                mapped_data[target_field] = df[source_field]
            else:
                logger.warning(f"Source column '{source_field}' not found in file")

        if not mapped_data:
            raise ValueError(
                "No columns could be mapped. Check your mapping configuration."
            )

        mapped_df = pd.DataFrame(mapped_data)
        logger.info(f"Mapped to {len(mapped_data)} columns: {list(mapped_data.keys())}")

        return mapped_df

    def _validate_schema(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Validate DataFrame against target schema."""
        errors = []
        target_cols = self.get_target_columns()

        # Check for required columns (ProductID)
        if "ProductID" not in df.columns and "ProductNumber" not in df.columns:
            errors.append("No ProductID or ProductNumber column found")

        # Filter to valid columns
        valid_columns = [col for col in df.columns if col in target_cols]
        invalid_columns = [col for col in df.columns if col not in target_cols]

        if invalid_columns:
            logger.warning(f"Invalid columns (will be skipped): {invalid_columns}")

        if not valid_columns:
            raise ValueError("No valid columns found. Check your mapping.")

        df = df[valid_columns]
        logger.info(f"Validated {len(valid_columns)} columns: {valid_columns}")

        return df, errors

    def _perform_import(
        self, df: pd.DataFrame, audit_id: int, batch_size: int
    ) -> ImportResultDTO:
        """
        Perform batch insert into database.

        Returns:
            ImportResultDTO with import summary
        """
        if df.empty:
            logger.warning("No data to import")
            return ImportResultDTO(
                status=ImportStatus.SUCCESS,
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                skipped_rows=0,
                errors=[],
                log_file=logger.handlers[0].baseFilename if logger.handlers else "",
            )

        total_rows = len(df)
        imported_rows = 0
        failed_rows = 0
        errors = []

        # Convert to list of dicts
        records = df.to_dict("records")

        # Process in batches
        for i in range(0, total_rows, batch_size):
            batch = records[i : i + batch_size]
            batch_num = (i // batch_size) + 1

            try:
                with myfactory_session() as session:
                    # Use bulk insert for performance
                    session.bulk_insert_mappings(self.table_name, batch)
                    session.commit()

                imported_rows += len(batch)
                logger.info(f"✅ Batch {batch_num}: Inserted {len(batch)} rows")

            except Exception as e:
                # Handle batch failure - try row by row
                logger.error(f"❌ Batch {batch_num} failed: {e}")
                failed_rows += self._insert_rows_individually(batch, errors)

        # Update audit
        self._update_audit(
            audit_id,
            ImportResultDTO(
                status=(
                    ImportStatus.SUCCESS if failed_rows == 0 else ImportStatus.FAILED
                ),
                total_rows=total_rows,
                imported_rows=imported_rows,
                failed_rows=failed_rows,
                skipped_rows=0,
                errors=errors,
                log_file=logger.handlers[0].baseFilename if logger.handlers else "",
            ),
            errors,
        )

        return ImportResultDTO(
            status=ImportStatus.SUCCESS if failed_rows == 0 else ImportStatus.FAILED,
            total_rows=total_rows,
            imported_rows=imported_rows,
            failed_rows=failed_rows,
            skipped_rows=0,
            errors=errors[:10],
            log_file=logger.handlers[0].baseFilename if logger.handlers else "",
        )

    def _insert_rows_individually(self, rows: List[Dict], errors: List[str]) -> int:
        """Insert rows one by one (fallback for batch failure)."""
        failed = 0

        for row in rows:
            try:
                with myfactory_session() as session:
                    session.execute(
                        text(
                            f"INSERT INTO {self.table_name} ({', '.join(row.keys())}) "
                            f"VALUES ({', '.join([':' + k for k in row.keys()])})"
                        ),
                        row,
                    )
                    session.commit()
            except Exception as e:
                failed += 1
                error_msg = f"Row failed: {row.get('ProductID', 'unknown')} - {e}"
                errors.append(error_msg)
                logger.warning(error_msg)

        return failed

    def _dry_run(
        self, df: pd.DataFrame, mapping: Dict[str, str], audit_id: int
    ) -> ImportResultDTO:
        """
        Execute dry-run with preview.

        Returns:
            ImportResultDTO with preview data in details
        """
        logger.info("=" * 60)
        logger.info("🔍 DRY RUN MODE - No changes will be made")
        logger.info("=" * 60)

        # Show mapping preview
        logger.info(f"Mapping ({len(mapping)} fields):")
        for source, target in mapping.items():
            logger.info(f"  {source} → {target}")

        # Show data preview
        logger.info(f"\nData preview ({len(df)} rows, {len(df.columns)} columns):")
        if not df.empty:
            logger.info(f"Columns: {list(df.columns)}")
            preview_rows = min(10, len(df))
            logger.info(f"First {preview_rows} rows:")
            print(df.head(preview_rows).to_string())

        # Validate data
        errors = []
        for idx, row in df.iterrows():
            if pd.isna(row.get("ProductID")):
                errors.append(f"Row {idx}: Missing ProductID")

        if errors:
            logger.warning(f"Found {len(errors)} issues in data")

        # Update audit
        self._update_audit(
            audit_id,
            ImportResultDTO(
                status=ImportStatus.DRY_RUN,
                total_rows=len(df),
                imported_rows=0,
                failed_rows=0,
                skipped_rows=0,
                errors=errors,
                log_file=logger.handlers[0].baseFilename if logger.handlers else "",
            ),
            errors,
        )

        logger.info("=" * 60)
        logger.info("✅ Dry run completed. No changes made.")
        logger.info("=" * 60)

        return ImportResultDTO(
            status=ImportStatus.DRY_RUN,
            total_rows=len(df),
            imported_rows=0,
            failed_rows=0,
            skipped_rows=0,
            errors=errors,
            log_file=logger.handlers[0].baseFilename if logger.handlers else "",
            details={
                "preview_rows": df.head(10).to_dict("records") if not df.empty else [],
                "columns": list(df.columns),
                "mapping": mapping,
            },
        )

    def _update_audit(self, audit_id: int, result: ImportResultDTO, errors: List[str]):
        """Update audit record with import results."""
        with local_session() as session:
            audit = (
                session.query(ImportAudit).filter(ImportAudit.id == audit_id).first()
            )
            if audit:
                audit.complete(
                    rows_processed=result.total_rows,
                    rows_succeeded=result.imported_rows,
                    rows_failed=result.failed_rows,
                    rows_skipped=result.skipped_rows,
                    error_message="; ".join(errors[:5]) if errors else None,
                    details=result.details,
                )
                session.commit()
                logger.debug(f"Audit {audit_id} updated")

    def _log_summary(self, result: ImportResultDTO, dry_run: bool):
        """Log import summary."""
        logger.info("=" * 60)
        if dry_run:
            logger.info("🔍 DRY RUN SUMMARY")
        else:
            logger.info("📊 IMPORT SUMMARY")
        logger.info("=" * 60)

        logger.info(f"Status: {result.status.value.upper()}")
        logger.info(f"Total rows: {result.total_rows}")

        if not dry_run:
            logger.info(f"✅ Successfully imported: {result.imported_rows}")
            if result.failed_rows:
                logger.info(f"❌ Failed rows: {result.failed_rows}")
            if result.skipped_rows:
                logger.info(f"⏭️ Skipped rows: {result.skipped_rows}")

        if result.errors:
            logger.warning(f"Errors: {len(result.errors)}")
            for error in result.errors[:5]:
                logger.warning(f"  - {error}")

        logger.info(f"Log file: {result.log_file}")
        logger.info("=" * 60)

    # ========== Utility Methods ==========

    def get_import_history(
        self, supplier_name: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get import history from audit log."""
        with local_session() as session:
            query = session.query(ImportAudit)
            if supplier_name:
                query = query.filter(ImportAudit.supplier_name == supplier_name)
            query = query.order_by(ImportAudit.started_at.desc()).limit(limit)

            return [audit.to_dict() for audit in query.all()]

    def get_last_import(self, supplier_name: str) -> Optional[Dict[str, Any]]:
        """Get the last import for a supplier."""
        history = self.get_import_history(supplier_name, limit=1)
        return history[0] if history else None

    def clear_cache(self):
        """Clear target columns cache."""
        self._target_columns = None


# ========== Singleton Accessor ==========

_importer: Optional[MyfactoryImporter] = None


def get_importer(batch_size: int = 1000, table_name: str = None) -> MyfactoryImporter:
    """Get or create the importer instance."""
    global _importer
    if _importer is None:
        _importer = MyfactoryImporter(batch_size, table_name)
    return _importer


# ========== Example Usage ==========
if __name__ == "__main__":
    importer = get_importer()

    # Import with config
    result = importer.import_file(
        {
            "file_path": "sample.csv",
            "supplier_name": "supplier_a",
            "dry_run": True,
            "batch_size": 100,
        }
    )

    print(f"Import result: {result.status}")
