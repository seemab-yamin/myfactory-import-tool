"""Core import logic for Myfactory with CSV/Excel parsing, batch insert, and audit logging."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from sqlalchemy import bindparam, text

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
    supplier_id,
    dry_run,
    batch_size,
    header_row_index,
    sheet_name,
    delimiter,
):
    importer = get_importer()
    payload = {
        "supplier_id": supplier_id,
        "file_path": str(file_path),
        "import_id": import_id,
        "dry_run": dry_run,
        "batch_size": batch_size,
    }
    return importer.import_file(
        payload,
        delimiter=delimiter,
        header_row_index=header_row_index,
        sheet_name=sheet_name,
    )


class MyfactoryImporter:

    def __init__(
        self,
        batch_size: int = 1000,
        auto_fetch_mapping: bool = True,
    ):
        self.config = get_config_manager().get()
        self.products_table = self.config.default_products_table
        self.attribute_values_table = self.config.default_attribute_values_table
        self.auto_fetch_mapping = auto_fetch_mapping
        self.batch_size = batch_size or self.config.default_batch_size
        self.mapper = get_mapper()
        self.db_manager = get_db_manager()
        self._target_columns = None

    def get_target_columns(self) -> List[str]:
        """Get target columns from the database."""
        if self._target_columns is None:
            columns = self.db_manager.get_table_columns(
                table_names=[self.products_table, self.attribute_values_table],
                use_cache=True,
            )
            self._target_columns = [col["name"] for col in columns]
        return self._target_columns

    def import_file(
        self,
        config: Union[ImportConfigDTO, Dict[str, Any]],
        header_row_index: int = 1,
        sheet_name: Optional[str] = None,
        delimiter: Optional[str] = None,
    ) -> ImportResultDTO:
        # Convert dict to DTO if needed
        if isinstance(config, dict):
            config = ImportConfigDTO(**config)
        supplier_id = config.supplier_id
        logger.info("=" * 60)
        logger.info(f"🚀 Starting import from: {config.file_path}")
        logger.info(f"   Table: {self.products_table}")
        logger.info(f"   Attribute Values Table: {self.attribute_values_table}")
        logger.info(f"   Dry run: {config.dry_run}")
        logger.info(f"   Batch size: {config.batch_size}")
        logger.info("=" * 60)

        # ── Resolve supplier (DB source of truth) ──
        supplier = self.mapper.get_supplier_by_id(supplier_id)
        if supplier:
            config.supplier_name = supplier.get("name")
        else:
            raise ValueError(
                f"Supplier id={supplier_id} not found. "
                "Please create it via Add Supplier first."
            )

        # Create audit record
        audit = ImportAudit.create_from_import(
            supplier_name=config.supplier_name,
            file_path=config.file_path,
            import_id=config.import_id,
            products_table=self.products_table,
            dry_run=config.dry_run,
        )
        with local_session() as session:
            session.add(audit)
            session.flush()
            audit_id = audit.id

        try:
            # 1. Read file
            df, _ = self._read_file(
                file_path=config.file_path,
                delimiter=delimiter,
                header_row_index=header_row_index,
                sheet_name=sheet_name,
            )

            # 2. Get mapping
            mapping = self.mapper.get_mapping_dict(supplier_id, active_only=True)
            logger.info(f"   Mapping source: DB ({len(mapping)} fields)")

            if not mapping:
                raise ValueError(
                    f"No mapping found for supplier '{supplier_id}'. "
                    "Please configure mappings first."
                )

            # 3. Apply mapping
            mapped_df = self._apply_mapping(df, mapping)

            # 5. validate step: to be implemented should return similar result data structure after validation
            validated_df, result = self._validate_data(mapped_df, mapping)
            if result.errors:
                result.status = ImportStatus.FAILED
            elif config.dry_run:
                result.status = ImportStatus.DRY_RUN
            else:
                result = self._perform_import(validated_df, config.batch_size, audit_id)

            # 6. Update audit
            result.audit_id = audit_id
            self._update_audit(audit_id, result, result.errors)

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
                    audit.error_message = json.dumps(
                        {
                            "friendly": "Import failed. Please check the logs for details.",
                            "technical": str(e),
                        }
                    )
                    audit.completed_at = datetime.utcnow()

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

    def _apply_mapping(self, df: pd.DataFrame, mapping) -> pd.DataFrame:
        # Handle prepopulated values and missing source fields
        mapped_data = {}
        for target_field, mapping_info in mapping.items():

            prepopulated_value = mapping_info.get("prepopulated_value")
            source_field = mapping_info.get("source_field")
            if source_field in df.columns:
                df[source_field] = df[source_field].fillna(prepopulated_value)
                mapped_data[target_field] = df[source_field]
            elif prepopulated_value:
                mapped_data[target_field] = pd.Series(
                    [prepopulated_value] * len(df), index=df.index
                )

        if not mapped_data:
            raise ValueError(
                "No columns could be mapped. Check your mapping configuration."
            )

        df = pd.DataFrame(mapped_data)
        # we drop all the columns with all NaN values after mapping
        df.dropna(axis=1, how="all", inplace=True)
        logger.info(f"Mapped to {len(mapped_data)} columns: {list(mapped_data.keys())}")
        return df

    def _validate_schema(
        self, df: pd.DataFrame, mapping: Dict[str, dict]
    ) -> Tuple[pd.DataFrame, List[Dict]]:
        """Validate and coerce DataFrame columns to mapped data types."""
        errors = []
        for col in df.columns:
            if col not in mapping:
                continue

            mapping_info = mapping[col]
            sql_type = mapping_info.get("data_type")
            normalized_type = self._normalize_sql_type(sql_type)

            try:
                if normalized_type == "string":
                    df[col] = df[col].astype(str)
                elif normalized_type == "integer":
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                elif normalized_type == "decimal":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                elif normalized_type == "datetime":
                    df[col] = pd.to_datetime(df[col], errors="coerce")
            except Exception as e:
                errors.append({"column": col, "reason": str(e)})

            # Capture rows with NaN after coercion (failed conversions)
            nan_rows = df[df[col].isna()].index
            for row_idx in nan_rows:
                errors.append(
                    {
                        "row": row_idx,
                        "column": col,
                        "value": df.iloc[row_idx][col],
                        "reason": f"Failed to coerce to {normalized_type}",
                    }
                )
        return df, errors

    def _normalize_sql_type(self, sql_type: str) -> str:
        """Normalize SQL type to category."""
        sql_type = sql_type.upper()
        if "VARCHAR" in sql_type or "TEXT" in sql_type:
            return "string"
        elif "INT" in sql_type:
            return "integer"
        elif "MONEY" in sql_type or "DECIMAL" in sql_type:
            return "decimal"
        elif "DATETIME" in sql_type or "DATE" in sql_type:
            return "datetime"
        return "string"

    def _validate_data(self, df: pd.DataFrame, mapping) -> ImportResultDTO:
        """Validate data and return ImportResultDTO with errors if any."""
        # call _validate_schema to validate data types and constraints.
        df, schema_errors = self._validate_schema(df, mapping)
        errors = schema_errors

        # Additional data validation can be added here (e.g., required fields)

        if errors:
            logger.warning(f"Validation found {len(errors)} issues")
            for err in errors:
                logger.warning(f"  - {err}")

        return df, ImportResultDTO(
            status=ImportStatus.SUCCESS if not errors else ImportStatus.FAILED,
            total_rows=len(df),
            imported_rows=0,
            failed_rows=0,
            skipped_rows=0,
            errors=errors,
            log_file=logger.handlers[0].baseFilename if logger.handlers else "",
        )

    def _perform_import(
        self, df: pd.DataFrame, batch_size: int, audit_id: str
    ) -> ImportResultDTO:
        """Perform batch insert into database."""
        # -------------------------------------------------------------------------
        # 1. Validate input and initialize import state
        # -------------------------------------------------------------------------
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
        inserted_count = 0
        updated_count = 0
        failed_rows = 0
        errors = []

        # Convert DataFrame rows to dictionaries for batch processing.
        records = df.to_dict("records")

        # -------------------------------------------------------------------------
        # 2. Determine target columns from the imported data
        # -------------------------------------------------------------------------
        # Product columns are all mapped fields except attribute fields.
        # Attribute columns are identified by the "Attr_" prefix.
        pt_cols = [col for col in records[0] if not col.startswith("Attr_")]
        avt_cols = [col for col in records[0] if col.startswith("Attr_")]

        # ProductID is generated by the import process.
        insert_pt_columns = pt_cols + ["ProductID"]

        # RecordID links the attribute row back to the product.
        # EntityID identifies the product entity in the attribute table.
        avt_columns = avt_cols + ["RecordID", "EntityID"]

        # ProductNumber is the business key used to find an existing product,
        # so it must never be changed during an update.
        update_pt_columns = [column for column in pt_cols if column != "ProductNumber"]

        # All currently mapped attribute columns are eligible for update.
        update_avt_columns = avt_cols[:]

        # -------------------------------------------------------------------------
        # 3. Build SQL statements used by each batch
        # -------------------------------------------------------------------------
        insert_pt_stmt = text(f"""
            INSERT INTO [{self.products_table}]
            ({", ".join(f"[{c}]" for c in insert_pt_columns)},
            [CreationDate], [ChangeDate])
            VALUES
            ({", ".join(f":{c}" for c in insert_pt_columns)},
            GETDATE(), GETDATE())
        """)

        insert_avt_stmt = text(f"""
            INSERT INTO [{self.attribute_values_table}]
            ({", ".join(f"[{c}]" for c in avt_columns)})
            VALUES
            ({", ".join(f":{c}" for c in avt_columns)})
        """)

        update_pt_columns_str = ", ".join(
            f"[{column}] = :{column}" for column in update_pt_columns
        )

        if update_pt_columns:
            update_pt_columns_str = ", ".join(
                f"[{column}] = :{column}" for column in update_pt_columns
            )

            update_pt_stmt = text(f"""
                UPDATE [{self.products_table}]
                SET {update_pt_columns_str},
                    [ChangeDate] = GETDATE()
                WHERE [ProductID] = :ProductID
            """)
        else:
            update_pt_stmt = text(f"""
                UPDATE [{self.products_table}]
                SET [ChangeDate] = GETDATE()
                WHERE [ProductID] = :ProductID
            """)

        # Used to determine whether an attribute row already exists for
        # an existing product.
        select_avt_stmt = text(f"""
            SELECT [RecordID], [EntityID]
            FROM [{self.attribute_values_table}]
            WHERE [RecordID] IN :record_ids
            AND [EntityID] = :entity_id
        """).bindparams(bindparam("record_ids", expanding=True))

        # Used when an attribute row already exists.
        update_avt_stmt = text(f"""
            UPDATE [{self.attribute_values_table}]
            SET {
                ", ".join(
                    f"[{column}] = :{column}"
                    for column in update_avt_columns
                )
            }
            WHERE [RecordID] = :RecordID
            AND [EntityID] = :EntityID
        """)

        # -------------------------------------------------------------------------
        # 4. Process records in batches
        # -------------------------------------------------------------------------
        for i in range(0, total_rows, batch_size):
            batch = records[i : i + batch_size]
            batch_num = (i // batch_size) + 1

            # ProductNumber is used to determine whether each product is
            # new or already exists in MSSQL.
            product_numbers = [
                row["ProductNumber"] for row in batch if row.get("ProductNumber")
            ]

            try:
                # ---------------------------------------------------------------------
                # Prepare containers for this batch
                # ---------------------------------------------------------------------
                pt_batch_with_ids = []
                avt_batch_with_ids = []

                with myfactory_session() as session:

                    # -----------------------------------------------------------------
                    # 1. Find existing products
                    # -----------------------------------------------------------------
                    # ProductNumber is the business key used to determine whether
                    # each imported row should be inserted or updated.
                    existing_products = session.execute(
                        text(f"""
                            SELECT [ProductID], [ProductNumber]
                            FROM [{self.products_table}]
                            WHERE [ProductNumber] IN :product_numbers
                        """).bindparams(bindparam("product_numbers", expanding=True)),
                        {"product_numbers": product_numbers},
                    ).all()

                    existing_products_by_number = {
                        row.ProductNumber: row.ProductID for row in existing_products
                    }

                    # -----------------------------------------------------------------
                    # 2. Split the batch into new and existing products
                    # -----------------------------------------------------------------
                    # Products not found by ProductNumber will be inserted.
                    to_insert = [
                        row
                        for row in batch
                        if row["ProductNumber"] not in existing_products_by_number
                    ]

                    # Existing products will be updated.
                    # ProductNumber itself is excluded from update_pt_columns,
                    # so the business key is never changed.
                    pt_to_update = [
                        {
                            key: value
                            for key, value in row.items()
                            if key in update_pt_columns
                        }
                        | {
                            "ProductID": existing_products_by_number[
                                row["ProductNumber"]
                            ]
                        }
                        for row in batch
                        if row["ProductNumber"] in existing_products_by_number
                    ]

                    avt_to_upsert = [
                        {key: value for key, value in row.items() if key in avt_cols}
                        | {
                            "RecordID": existing_products_by_number[
                                row["ProductNumber"]
                            ],
                            "EntityID": self.config.products_entity_id,
                        }
                        for row in batch
                        if row["ProductNumber"] in existing_products_by_number
                    ]

                    # -----------------------------------------------------------------
                    # 3. Find existing attribute rows for existing products
                    # -----------------------------------------------------------------
                    # Attribute rows are identified by:
                    #   RecordID = ProductID
                    #   EntityID = configured product entity
                    record_ids = [row["ProductID"] for row in pt_to_update]

                    existing_avt_records = []

                    if record_ids:
                        existing_avt_records = session.execute(
                            select_avt_stmt,
                            {
                                "record_ids": record_ids,
                                "entity_id": self.config.products_entity_id,
                            },
                        ).all()
                    else:
                        existing_avt_records = []

                    existing_avt_record_ids = {
                        row.RecordID for row in existing_avt_records
                    }

                    # -------------------------------------------------------------------------
                    # 4. Prepare attribute rows for existing products that don't have one
                    # -------------------------------------------------------------------------
                    # An existing product may have been created directly in CRM without a
                    # corresponding row in tdAttributeValues. In that case, create the
                    # missing attribute row instead of attempting an UPDATE that affects 0 rows.
                    avt_to_insert = [
                        {key: value for key, value in row.items() if key in avt_cols}
                        | {
                            "RecordID": row["RecordID"],
                            "EntityID": self.config.products_entity_id,
                        }
                        for row in avt_to_upsert
                        if row["RecordID"] not in existing_avt_record_ids
                    ]

                    avt_to_update = [
                        {key: value for key, value in row.items() if key in avt_cols}
                        | {
                            "RecordID": row["RecordID"],
                            "EntityID": self.config.products_entity_id,
                        }
                        for row in avt_to_upsert
                        if row["RecordID"] in existing_avt_record_ids
                    ]

                    # -------------------------------------------------------------------------
                    # 5. Prepare new products and their attribute rows
                    # -------------------------------------------------------------------------
                    for row in to_insert:
                        # Generate the ProductID before inserting the product so the same ID
                        # can be used as RecordID in tdAttributeValues.
                        product_id = get_next_record_id(session, "tdProducts")

                        # Product record
                        pt_batch_with_ids.append(
                            {key: value for key, value in row.items() if key in pt_cols}
                            | {"ProductID": product_id}
                        )

                        # Attribute record linked to the newly created product
                        avt_batch_with_ids.append(
                            {
                                key: value
                                for key, value in row.items()
                                if key in avt_cols
                            }
                            | {
                                "RecordID": product_id,
                                "EntityID": self.config.products_entity_id,
                            }
                        )

                    # -------------------------------------------------------------------------
                    # 6. Insert new products and their attribute rows
                    # -------------------------------------------------------------------------
                    if pt_batch_with_ids:
                        session.execute(insert_pt_stmt, pt_batch_with_ids)

                        session.execute(insert_avt_stmt, avt_batch_with_ids)

                        inserted_count += len(pt_batch_with_ids)

                    # -------------------------------------------------------------------------
                    # 7. Update existing products and their attribute rows
                    # -------------------------------------------------------------------------
                    if pt_to_update:
                        # Update product fields for existing products.
                        session.execute(
                            update_pt_stmt,
                            pt_to_update,
                        )

                        # Only process attributes when the current import contains
                        # attribute mappings.
                        if update_avt_columns:

                            # Some existing products may not have an attribute row yet.
                            # Create the missing rows first.
                            if avt_to_insert:
                                session.execute(
                                    insert_avt_stmt,
                                    avt_to_insert,
                                )

                            # Update attribute values for products that already have
                            # an attribute row.
                            if avt_to_update:
                                session.execute(
                                    update_avt_stmt,
                                    avt_to_update,
                                )

                        updated_count += len(pt_to_update)

                # -------------------------------------------------------------------------
                # 8. Update import progress after the batch succeeds
                # -------------------------------------------------------------------------
                imported_rows = inserted_count + updated_count

                self._update_audit_progress(
                    audit_id=audit_id,
                    processed=imported_rows,
                    total=total_rows,
                )

                logger.info(
                    f"✅ Batch {batch_num}: "
                    f"Inserted {inserted_count} | "
                    f"Updated {updated_count}"
                )
            # -----------------------------------------------------------------
            # Handle batch failure
            # -----------------------------------------------------------------
            except Exception as e:
                logger.error(
                    f"❌ Batch {batch_num} failed: {e}",
                    exc_info=True,
                )

                # Mark every record in the failed batch as failed.
                failed_rows += len(batch)

                # Keep the error message for the final import result.
                errors.append(f"Batch {batch_num} failed: {e}")

        # -------------------------------------------------------------------------
        # Build final import result
        # -------------------------------------------------------------------------
        # The import is successful only when every input row was processed.
        status = (
            ImportStatus.SUCCESS if imported_rows == total_rows else ImportStatus.FAILED
        )

        return ImportResultDTO(
            status=status,
            total_rows=total_rows,
            imported_rows=imported_rows,
            failed_rows=failed_rows,
            skipped_rows=0,
            # Return only the first 10 errors to avoid an excessively large response.
            errors=errors[:10],
            log_file=(logger.handlers[0].baseFilename if logger.handlers else ""),
        )

    def _update_audit(self, audit_id: int, result: ImportResultDTO, errors: List[str]):
        """Update audit record with import results."""
        with local_session() as session:
            audit = (
                session.query(ImportAudit).filter(ImportAudit.id == audit_id).first()
            )
            if audit:
                error_message = (
                    json.dumps(
                        {
                            "friendly": "Import completed with errors. Please check the logs for details.",
                            "technical": "; ".join(errors[:5]),
                        }
                    )
                    if errors
                    else None
                )
                audit.complete(
                    rows_processed=result.total_rows,
                    rows_succeeded=result.imported_rows,
                    rows_failed=result.failed_rows,
                    rows_skipped=result.skipped_rows,
                    error_message=error_message,
                    details=result.details,
                )
                logger.debug(f"Audit {audit_id} updated")

    def _update_audit_progress(
        self,
        audit_id: int,
        processed: int,
        total: int,
    ):
        with local_session() as session:
            audit = (
                session.query(ImportAudit).filter(ImportAudit.id == audit_id).first()
            )
            if audit:
                audit.rows_processed = processed
                audit.status = ImportStatus.RUNNING.value

                if audit.details is None:
                    audit.details = {}

                audit.details["progress"] = {
                    "processed": processed,
                    "total": total,
                    "percentage": round((processed / total) * 100, 2),
                }

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
        self,
        supplier_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Get import history from audit log with pagination.

        Returns:
            (records, total_count) — `total_count` is the full count matching the
            filter, ignoring limit/offset, so callers can compute total pages.
        """
        with local_session() as session:
            query = session.query(ImportAudit)
            if supplier_name:
                query = query.filter(ImportAudit.supplier_name == supplier_name)

            # ✅ Count BEFORE applying pagination
            total_count = query.count()

            # Apply ordering + pagination
            rows = (
                query.order_by(ImportAudit.started_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            return [audit.to_dict() for audit in rows], total_count

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


def get_next_record_id(session, products_table):
    result = session.execute(
        text("""
            SET NOCOUNT ON;
            DECLARE @id INT;
            EXEC spwfGetNextRecordID
                @sTable=:table_name,
                @lRecordID=@id OUTPUT;
            SELECT @id AS ProductID;
        """),
        {"table_name": products_table},
    )

    return result.scalar_one()


# ========== Singleton Accessor ==========

_importer: Optional[MyfactoryImporter] = None


def get_importer() -> MyfactoryImporter:
    """Get or create the importer instance."""
    global _importer
    if _importer is None:
        _importer = MyfactoryImporter()
    return _importer
