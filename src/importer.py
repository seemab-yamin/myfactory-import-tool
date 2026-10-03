"""Core import logic for Myfactory with CSV/Excel parsing, batch insert, and audit logging."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from sqlalchemy import text

from src.config_manager import get_config_manager
from src.db import get_db_manager, local_session, myfactory_session
from src.logger import get_logger
from src.mapper import get_mapper
from src.models import ImportAudit
from src.schemas.dto import (
    ImportConfigDTO,
    ImportResultDTO,
    ImportStatus,
)

logger = get_logger(__name__)


def run_import(
    import_id: str,
    file_path,
    supplier_id=None,
    supplier=None,
    dry_run=False,
    batch_size=1000,
    header_row_index=None,
    sheet_name=None,
):
    importer = get_importer()
    payload = {
        "file_path": str(file_path),
        "import_id": import_id,
        "dry_run": dry_run,
        "batch_size": batch_size,
        "header_row_index": header_row_index,
        "sheet_name": sheet_name,
    }
    if supplier_id is not None:
        payload["supplier_id"] = supplier_id
    else:
        payload["supplier_name"] = supplier

    return importer.import_file(payload)


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
        self.auto_fetch_mapping = auto_fetch_mapping
        self.batch_size = batch_size or get_config_manager().get().default_batch_size
        self.table_name = table_name
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
        self,
        config: Union[ImportConfigDTO, Dict[str, Any]],
        header_row_index: Optional[int] = None,
        sheet_name: Optional[str] = None,
        delimiter: Optional[str] = None,
    ) -> ImportResultDTO:
        # Convert dict to DTO if needed
        if isinstance(config, dict):
            config = ImportConfigDTO(**config)

        logger.info("=" * 60)
        logger.info(f"🚀 Starting import from: {config.file_path}")
        logger.info(f"   Supplier: id={config.supplier_id} name={config.supplier_name}")
        logger.info(f"   Table: {config.table_name}")
        logger.info(f"   Dry run: {config.dry_run}")
        logger.info(f"   Batch size: {config.batch_size}")
        logger.info("=" * 60)

        # ── Resolve supplier (DB source of truth) ──
        supplier = None
        if config.supplier_id is not None:
            supplier = self.mapper.get_supplier_by_id(config.supplier_id)
            if supplier:
                config.supplier_name = supplier.get("name") or config.supplier_name
            else:
                raise ValueError(
                    f"Supplier id={config.supplier_id} not found. "
                    "Please create it via Add Supplier first."
                )
        elif config.supplier_name:
            supplier = self.mapper.get_supplier(config.supplier_name)
            if not supplier:
                raise ValueError(
                    f"Supplier '{config.supplier_name}' not found. "
                    "Please create it via Add Supplier first."
                )
        else:
            raise ValueError("Neither supplier_id nor supplier_name was provided.")

        # ── Normalize supplier shape (dict vs ORM) ──
        if isinstance(supplier, dict):
            supplier_id = supplier.get("id")
            db_header_row = supplier.get("header_row_index") or 1
            db_sheet_name = supplier.get("sheet_name")
            db_delimiter = supplier.get("delimiter") or ","
        else:
            supplier_id = supplier.id
            db_header_row = supplier.header_row_index or 1
            db_sheet_name = supplier.sheet_name
            db_delimiter = supplier.delimiter or ","

        # Create audit record
        audit = ImportAudit.create_from_import(
            supplier_name=config.supplier_name,
            file_path=config.file_path,
            import_id=config.import_id,
            table_name=config.table_name,
            dry_run=config.dry_run,
        )
        with local_session() as session:
            session.add(audit)
            session.flush()
            audit_id = audit.id

        try:
            # ── Resolve final config: explicit arg → DTO → DB → default ──
            resolved_header_row = (
                header_row_index if header_row_index is not None else db_header_row
            )
            resolved_sheet_name = (
                sheet_name if sheet_name is not None else db_sheet_name
            )
            resolved_delimiter = delimiter if delimiter else db_delimiter

            logger.info(f"   header_row_index={resolved_header_row} ")
            logger.info(f"   sheet_name={resolved_sheet_name} ")
            logger.info(f"   delimiter='{resolved_delimiter}' ")

            # 1. Read file
            df, available_sheets = self._read_file(
                file_path=config.file_path,
                delimiter=resolved_delimiter,
                header_row_index=resolved_header_row,
                sheet_name=resolved_sheet_name,
            )

            # 2. Get mapping
            if config.mapping:
                mapping = config.mapping
                logger.info(f"   Mapping source: DTO ({len(mapping)} fields)")
            else:
                mapping = self.mapper.get_mapping_dict(supplier_id, active_only=True)
                logger.info(f"   Mapping source: DB ({len(mapping)} fields)")

            if not mapping:
                raise ValueError(
                    f"No mapping found for supplier '{config.supplier_name}'. "
                    "Please configure mappings first."
                )

            # 3. Apply mapping
            mapped_df = self._apply_mapping(df, mapping)

            # 4. Validate schema
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
        self,
        file_path: str,
        delimiter: Optional[str] = None,
        header_row_index: int = 1,
        sheet_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Read CSV or Excel file with unified config."""

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        available_sheets = []

        try:
            if ext == ".csv":
                if sheet_name:
                    logger.warning(f"sheet_name='{sheet_name}' ignored for CSV file")
                df = self._read_csv(path, delimiter, header_row_index)
            elif ext in [".xlsx", ".xls"]:
                df, available_sheets = self._read_excel(
                    path, sheet_name, header_row_index
                )
            else:
                raise ValueError(
                    f"Unsupported file type: {ext}. Please use CSV or Excel."
                )

            if df.empty:
                logger.warning("File is empty")

            logger.info(f"✅ Read {len(df)} rows, {len(df.columns)} columns")
            logger.info(f"   Columns: {list(df.columns)}")

            return df, available_sheets

        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            raise

    def _read_csv(
        self,
        path: Path,
        delimiter: Optional[str] = None,
        header_row_index: int = 1,
    ) -> pd.DataFrame:
        """Read CSV with optional custom header row."""
        skip = max(header_row_index - 1, 0)

        if delimiter is None:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(4096)
            try:
                delimiter = csv.Sniffer().sniff(sample).delimiter
            except csv.Error:
                delimiter = ","

        df = pd.read_csv(
            path,
            delimiter=delimiter,
            skiprows=skip,
            header=0,
            encoding="utf-8",
            on_bad_lines="warn",
        )

        if df.columns.isna().all():
            logger.warning("Header row resolved to all-NaN. Generating col_1..col_N")
            df.columns = [f"col_{i+1}" for i in range(len(df.columns))]

        return df

    def _read_excel(
        self,
        path: Path,
        sheet_name: Optional[str] = None,
        header_row_index: int = 1,
    ) -> pd.DataFrame:
        """Read Excel with optional sheet selection and custom header row."""
        skip = max(header_row_index - 1, 0)

        available_sheets = self.list_excel_sheets(path)
        effective_sheet = sheet_name
        if sheet_name and sheet_name not in available_sheets:
            logger.warning(
                f"Sheet '{sheet_name}' not found. "
                f"Available: {available_sheets}. Falling back to first sheet."
            )
            effective_sheet = None
        elif sheet_name is None:
            logger.info(
                f"No sheet_name provided. Using first sheet: {available_sheets[0]}"
            )

        df = pd.read_excel(
            path,
            sheet_name=effective_sheet if effective_sheet else 0,
            skiprows=skip,
            header=0,
        )

        if df.columns.isna().all():
            logger.warning("Header row resolved to all-NaN. Generating col_1..col_N")
            df.columns = [f"col_{i+1}" for i in range(len(df.columns))]

        return df, available_sheets

    def _apply_mapping(self, df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
        """Apply field mapping to DataFrame."""

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

        if "ProductNumber" not in df.columns:
            errors.append(
                "No ProductNumber column found - this is required for product identification"
            )

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
        """Perform batch insert into database."""

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

        records = df.to_dict("records")

        for i in range(0, total_rows, batch_size):
            batch = records[i : i + batch_size]
            batch_num = (i // batch_size) + 1

            try:
                with myfactory_session() as session:
                    session.bulk_insert_mappings(self.table_name, batch)
                    session.commit()

                imported_rows += len(batch)
                logger.info(f"✅ Batch {batch_num}: Inserted {len(batch)} rows")

            except Exception as e:
                logger.error(f"❌ Batch {batch_num} failed: {e}")
                failed_rows += self._insert_rows_individually(batch, errors)

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
                error_msg = f"Row failed: {row.get('ProductNumber', 'unknown')} - {e}"
                errors.append(error_msg)
                logger.warning(error_msg)

        return failed

    def _dry_run(
        self, df: pd.DataFrame, mapping: Dict[str, str], audit_id: int
    ) -> ImportResultDTO:
        """Execute dry-run with preview."""

        logger.info("=" * 60)
        logger.info("🔍 DRY RUN MODE - No changes will be made")
        logger.info("=" * 60)

        logger.info(f"Mapping ({len(mapping)} fields):")
        for source, target in mapping.items():
            logger.info(f"  {source} → {target}")

        logger.info(f"\nData preview ({len(df)} rows, {len(df.columns)} columns):")
        if not df.empty:
            logger.info(f"Columns: {list(df.columns)}")
            preview_rows = min(10, len(df))
            logger.info(f"First {preview_rows} rows:")
            logger.info("\n" + df.head(preview_rows).to_string())

        errors = []
        for idx, row in df.iterrows():
            if pd.isna(row.get("ProductNumber")):
                errors.append(f"Row {idx}: Missing ProductNumber")

        if errors:
            logger.warning(f"Found {len(errors)} issues in data")

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

    def list_excel_sheets(self, file_path: str) -> List[str]:
        """Return sheet names for an Excel file. Empty list for CSV."""
        path = Path(file_path)
        if path.suffix.lower() not in [".xlsx", ".xls"]:
            return []
        try:
            return pd.ExcelFile(path).sheet_names
        except Exception as e:
            logger.error(f"Failed to list sheets: {e}")
            return []


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

    result = importer.import_file(
        {
            "file_path": "sample.csv",
            "supplier_name": "supplier_a",
            "dry_run": True,
            "batch_size": 100,
        }
    )

    print(f"Import result: {result.status}")
