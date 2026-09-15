# PROJECT_DOCUMENTATION_v1.0

This document captures the current implementation of the MyFactory import tool, plus the requested operational sections for configuration, dependencies, authentication, error handling, performance, and background jobs.

Where the request mentions names that are not present in the current codebase, the document calls out the current equivalent implementation.

## Overview

The project is a FastAPI-based CSV/Excel import tool for MyFactory CRM. It provides:

- a web UI for upload, mapping, and schema inspection
- a CLI for setup, import, mapping management, and schema viewing
- a local SQLite database for application data and cached schema metadata
- an MSSQL/MyFactory connection for live target schema lookup and import operations

Primary code paths:

- `src/main.py` launches the CLI or web UI
- `src/api/routes.py` exposes HTML pages and API endpoints
- `src/importer.py` performs file ingestion, mapping, validation, and import
- `src/mapper.py` stores and retrieves supplier mappings
- `src/schema_scanner.py` reads cached and live schema metadata
- `src/models.py` defines the local SQLAlchemy models
- `src/db.py` manages local SQLite and remote MSSQL sessions

## Configuration

### Environment variables

The current codebase reads these environment variables from `config/.env` through `src/config_manager.py`:

- `DB_SERVER` - MSSQL server host or instance name
- `DB_DATABASE` - target database name
- `DB_USERNAME` - SQL authentication username
- `DB_PASSWORD` - SQL authentication password
- `DB_DRIVER` - ODBC driver name, default `ODBC Driver 17 for SQL Server`
- `DB_TRUSTED_CONNECTION` - `True` or `False`
- `DB_PORT` - MSSQL port, default `1433`
- `DB_CONNECTION_TIMEOUT` - connection timeout in seconds, default `30`

Important implementation note:

- The code does not currently read `MSSQL_CONNECTION_STRING` directly.
- The code does not currently read `SQLITE_PATH` directly.
- The MSSQL connection string is derived internally from the variables above.
- The local SQLite path is derived from `src/db.py` as `BASE_DIR / "data" / "mappings.db"`.

### `config.json` structure

`config/config.json` is loaded after defaults and before `.env`. The current structure is:

```json
{
  "db_server": "TCS135\\SQLEXPRESS",
  "db_database": "master",
  "db_driver": "ODBC Driver 17 for SQL Server",
  "db_trusted_connection": true,
  "db_port": 1433,
  "db_connection_timeout": 30,
  "auth_method": "windows",
  "default_products_table": "tdProducts",
  "default_supplier": "default",
  "default_delimiter": ",",
  "default_batch_size": 1000,
  "skip_header": true,
  "log_level": "INFO",
  "log_max_bytes": 5000000,
  "log_backup_count": 3,
  "app_name": "MyFactory Import Tool",
  "app_version": "1.0.0"
}
```

### Directory layout

Current code-resolved locations:

- Local app base: `~/Documents/MyFactoryImportTool/`
- Local SQLite DB: `~/Documents/MyFactoryImportTool/data/mappings.db`
- Logs: `~/Documents/MyFactoryImportTool/logs/`
- Uploads: `./uploads/` relative to the current working directory / project root

Requested layout in the prompt:

- `~/Documents/MyFactoryImporter/uploads/`
- `~/Documents/MyFactoryImporter/logs/`
- `~/Documents/MyFactoryImporter/db/`

That requested layout is not the exact current implementation. If you want the runtime to match it exactly, `src/paths.py`, `src/db.py`, `src/logger.py`, and `src/api/routes.py` would need to be aligned to the same base directory.

## Dependencies

Documented runtime requirements:

- Python 3.10+
- FastAPI 0.104+
- SQLAlchemy 2.0+
- pyodbc for MSSQL connectivity
- APScheduler 3.10+

Current `requirements.txt` includes the practical runtime packages used by the app:

- `pandas`
- `pydantic`
- `python-dotenv`
- `pyodbc`
- `fastapi`
- `uvicorn`
- `sqlalchemy`
- `openpyxl`
- `keyring`
- `python-multipart`
- `jinja2`
- `starlette`
- `rich`

Implementation note:

- APScheduler is not currently imported or wired into the codebase.
- The dependency list in `requirements.txt` also does not currently include APScheduler.
- The documentation below records the intended background-job section so the project can be extended consistently when scheduling is added.

## Authentication

### MSSQL

The MyFactory connection uses integrated Windows authentication when `db_trusted_connection=True`.

Current behavior:

- `src/config_manager.AppSettings.get_sqlalchemy_url()` builds an MSSQL URL with `Trusted_Connection=yes` when trusted auth is enabled.
- `src.db.DatabaseManager.myfactory_session()` uses the configured SQLAlchemy engine and session factory.
- The `myfactory_session` context manager is the current MSSQL access path used by import and schema-related code.

If SQL authentication is enabled instead:

- `DB_USERNAME` and `DB_PASSWORD` are used.
- The connection string switches to UID/PWD mode.

### Web API

- The web API currently has no authentication or authorization layer.
- It is intended as an internal tool.
- If that changes, the API route layer and UI entry points will need explicit auth middleware and/or dependency checks.

## Error Handling & Retry

### Batch import failure fallback

The import flow is designed to be resilient during batch inserts:

- The importer batches rows before inserting into MSSQL.
- If a batch insert fails, the code falls back to row-level insert for finer-grained failure handling.
- This prevents a single bad row from necessarily killing the entire import.

### Schema validation errors

- Schema validation happens before the write phase in `src/importer.py`.
- Validation errors are collected and attached to the import result.
- If the import ultimately fails, the exception message is stored in `ImportAudit.error_message`.

### MSSQL connection retry / timeout

Current implementation details:

- Connection timeout is configurable through `DB_CONNECTION_TIMEOUT` and defaults to 30 seconds.
- SQLAlchemy engine creation uses `pool_pre_ping=True` and `pool_timeout=30` in `src/db.py`.
- There is no explicit exponential backoff or multi-attempt retry loop in the current code.

So the effective behavior is:

- one connection attempt per operation path
- timeout enforcement through the ODBC/SQLAlchemy layers
- stale connection detection via pool pre-ping

If you want an explicit retry policy, that should be added as a separate wrapper around MSSQL connection and/or import execution.

## Performance Characteristics

### Batch size

- Default batch size in the operational flow is 1000.
- It can be overridden from the CLI, API form submission, or import config payload.
- `ImportConfigDTO.batch_size` currently defaults to 100 in code, so the effective default depends on the caller.

Practical callers currently using 1000 by default:

- CLI import command
- web upload route
- `MyfactoryImporter.__init__`
- `config.json` default value

### Excel sheets

- Excel files are read with pandas.
- If the workbook contains multiple sheets, the importer reads all sheets and concatenates them into a single DataFrame.
- There is no hard-coded sheet-count cap in the current implementation.
- Practical limits are workbook size, memory, and pandas/openpyxl performance.

### Schema cache

- Cached schema lives in local SQLite via the `target_fields` table.
- `refresh_cache=true` on `GET /api/schema` bypasses the cache and reads live MSSQL metadata.
- The CLI `schema --refresh` path also refreshes the cache manually.
- Schema drift checks refresh the cached target field rows after comparison.

## Background Jobs (APScheduler)

Current codebase status:

- APScheduler is not currently wired into the app startup path.
- There is no `app.on_event("startup")` job registration in the current source tree.

Requested operational behavior to document for the intended scheduler layer:

- Schema drift check runs every 30 minutes.
- The scheduler is started during app startup.
- Drift activity is logged to `~/Documents/MyFactoryImporter/logs/schema_drift.log`.

Current practical equivalent behavior:

- Drift checks can be triggered manually via `POST /api/schema/check`.
- The mappings list page also performs a best-effort drift check on page load.
- Drift results are stored in the local `schema_change_log` table.

## Data Flow: CSV Upload → Mapping → Import → Database

1. **Upload entry point**
   - User uploads CSV or Excel through the web UI or CLI.
   - The upload route saves the file under `uploads/` with a timestamped name.

2. **Mapping resolution**
   - The importer loads the supplier mapping from SQLite via `FieldMapper`.
   - Source columns are translated into target MyFactory column names.
   - Missing source columns are logged and skipped.

3. **Schema validation**
   - The mapped DataFrame is compared against the target schema.
   - Invalid columns are removed.
   - Missing required identity/identification fields are reported.

4. **Dry run or import**
   - In dry-run mode, the importer returns preview data, column lists, mapping info, and validation issues without writing to MSSQL.
   - In normal mode, rows are inserted into MSSQL in batches.

5. **Fallback and audit**
   - If a batch insert fails, the importer falls back to row-level insertion.
   - Every run creates an `ImportAudit` record in local SQLite.
   - Final status, row counts, error text, and timestamps are written back to the audit row.

6. **Post-import visibility**
   - Import history is queryable through the API and CLI.
   - Schema drift and mapping state remain visible through the local database and UI.

## Functions

### `src/importer.py`

- `run_import(file_path, supplier, dry_run, batch_size)`
  - Convenience wrapper that instantiates the shared importer and runs a file import.
- `MyfactoryImporter.__init__(batch_size=1000, table_name=None, auto_fetch_mapping=True)`
  - Initializes importer state, target table, mapper, DB manager, and batch settings.
- `MyfactoryImporter.get_target_columns()`
  - Returns cached target column names for the active MyFactory table.
- `MyfactoryImporter.import_file(config)`
  - Main orchestration method for reading, mapping, validating, importing, and auditing.
- `MyfactoryImporter._read_file(file_path, delimiter=None)`
  - Dispatches to CSV or Excel parsing based on file extension.
- `MyfactoryImporter._read_csv(path, delimiter=None)`
  - Reads CSV files with delimiter detection and encoding fallback.
- `MyfactoryImporter._read_excel(path)`
  - Reads Excel workbooks and merges sheets when needed.
- `MyfactoryImporter._apply_mapping(df, mapping)`
  - Renames source columns to target columns using the supplier mapping.
- `MyfactoryImporter._validate_schema(df)`
  - Filters mapped columns against the target schema and collects validation errors.
- `MyfactoryImporter._perform_import(df, audit_id, batch_size)`
  - Executes the batch insert path into MSSQL.
- `MyfactoryImporter._insert_rows_individually(...)`
  - Fallback row-by-row insert path after a batch failure.
- `MyfactoryImporter._dry_run(...)`
  - Produces preview-only results without writing data.
- `MyfactoryImporter._update_audit(audit_id, result, errors)`
  - Finalizes the local audit row with status and error information.
- `MyfactoryImporter._log_summary(result, dry_run)`
  - Writes a final summary to the logger.
- `MyfactoryImporter.get_import_history(supplier, limit)`
  - Returns recent import audit records.
- `MyfactoryImporter.get_last_import(supplier)`
  - Returns the newest audit row for a supplier.
- `MyfactoryImporter.clear_cache()`
  - Clears cached schema or target metadata held by the importer.
- `get_importer()`
  - Singleton accessor for the shared importer instance.

### `src/mapper.py`

- `FieldMapper.__init__()`
  - Initializes in-memory caches for mapping and supplier lookup.
- `FieldMapper.get_mappings(supplier_id, active_only=True)`
  - Loads mappings for a supplier from the local database.
- `FieldMapper.mapping_name_exists(mapping_name)`
  - Checks whether a supplier or mapping name already exists.
- `FieldMapper.save_mappings(supplier_name, source_fields, mappings, is_new_supplier=False)`
  - Creates or updates a supplier mapping record.
- `FieldMapper.delete_supplier(supplier_id)`
  - Deletes a supplier and its associated mapping data.
- `FieldMapper.get_all_suppliers()`
  - Returns all suppliers ordered by name.
- `FieldMapper.get_supplier_by_id(supplier_id)`
  - Returns a supplier payload for detail pages and API responses.
- `FieldMapper.get_source_fields(supplier_id)`
  - Returns stored source field names for a supplier.
- `FieldMapper.get_target_fields()`
  - Returns all cached target fields from SQLite.
- `FieldMapper.apply_mapping(df, mapping, strict=False)`
  - Applies a source-to-target mapping to a DataFrame.
- `FieldMapper.clear_cache()`
  - Clears the in-memory mapping caches.
- `FieldMapper._get_supplier_id(supplier_name)`
  - Internal helper for supplier resolution by name.
- `FieldMapper._get_or_create_supplier(supplier_name, source_fields=None)`
  - Resolves or creates supplier metadata.
- `get_mapper()`
  - Singleton accessor for the shared `FieldMapper` instance.
- `sync_supplier_json(supplier, schema_diff)`
  - Reconciles a supplier’s mapping JSON after schema drift.
- `sync_all_suppliers(schema_diff, session)`
  - Applies drift cleanup across all suppliers.

### `src/schema_scanner.py`

- `SchemaScanner.__init__()`
  - Binds the database manager for schema access.
- `SchemaScanner.get_table_schema(table_name="tdProducts", use_cache=True, sort_by=None)`
  - Returns schema rows either from SQLite cache or live MSSQL metadata.
- `SchemaScanner.get_live_schema_as_target_fields(table_name="tdProducts")`
  - Returns live MSSQL schema as `TargetField` objects.
- `SchemaScanner.get_column_types(table_name="tdProducts")`
  - Returns a name-to-type mapping for a table.
- `SchemaScanner.table_exists(table_name)`
  - Checks whether a table exists in the target database.
- `SchemaScanner.get_schema_summary(table_name="tdProducts")`
  - Returns a compact schema summary for UI/API consumers.
- `get_scanner()`
  - Singleton accessor for the scanner.
- `get_table_schema(table_name="tdProducts")`
  - Module-level wrapper for `SchemaScanner.get_table_schema`.
- `get_live_schema_as_target_fields(table_name="tdProducts")`
  - Module-level wrapper for live schema retrieval.
- `compare_schemas(cached_fields, live_fields)`
  - Compares cached vs live schema and reports added, removed, and changed columns.
- `_is_length_narrowed(old_len, new_len)`
  - Helper for detecting narrowing column lengths.
- `_is_type_narrowed(old_type, new_type)`
  - Helper for detecting potentially breaking type changes.
- `_base_type(data_type)`
  - Normalizes SQL type strings to a base type.
- `detect_and_log_schema_changes(table_name="tdProducts", apply_sync=True)`
  - Compatibility wrapper around the schema drift service.

## SQLAlchemy Models

### `src/models.py`

- `Supplier`
  - Local supplier mapping record.
  - Fields: `id`, `name`, `source_fields`, `mappings`, `created_at`, `updated_at`, `schema_changed_at`, `schema_changed_flag`.
- `SchemaChangeLog`
  - Audit trail for schema drift checks.
  - Fields: `id`, `checked_at`, `added_fields`, `removed_fields`, `suppliers_synced`, `details`.
- `ImportStatus`
  - Enum values: `pending`, `running`, `success`, `failed`, `dry_run`.
- `TargetField`
  - Cached target schema row for a MyFactory table.
  - Fields: `id`, `table_name`, `field_name`, `data_type`, `max_length`, `is_nullable`, `is_identity`, `default_value`, `discovered_at`, `updated_at`.
- `ImportAudit`
  - Audit row for each import operation.
  - Fields: `id`, `supplier_name`, `file_name`, `file_path`, `table_name`, `rows_processed`, `rows_succeeded`, `rows_failed`, `rows_skipped`, `status`, `error_message`, `dry_run`, `started_at`, `completed_at`, `details`.
- `ImportSettings`
  - Key/value store for global app settings.
  - Fields: `id`, `key`, `value`, `description`, `is_encrypted`, `created_at`, `updated_at`.
- `ImportConfigDTO`
  - Runtime import configuration payload.
  - Fields: `file_path`, `mapping`, `delimiter`, `batch_size`, `dry_run`, `table_name`, `supplier_name`, `skip_header`.
- `ImportResultDTO`
  - Summary object returned by import operations.
  - Fields: `status`, `total_rows`, `imported_rows`, `failed_rows`, `skipped_rows`, `errors`, `log_file`, `audit_id`, `details`.
- `get_table_name(table_name=None)`
  - Returns the configured target table or a default fallback.

### Relationships

The current model set is lightweight and does not declare explicit ORM `relationship()` links between tables. The data model is mostly linked by IDs and JSON payloads.

## API Endpoints

### HTML pages

- `GET /` → home page
- `GET /mappings-list` → supplier mapping list page, with best-effort schema drift check
- `GET /show-mapping/{supplier_id}` → supplier detail page
- `GET /add-mapping` → add mapping page

### API routes

- `GET /health` → basic health/status response
- `POST /upload` → upload a CSV/Excel file and either dry-run or start background import
- `GET /history` → list import history, optionally filtered by supplier
- `GET /history/{audit_id}` → return a single audit record
- `GET /api/mappings-list` → list all suppliers
- `GET /api/mapping_name/exists/{supplier_name}` → check whether a supplier exists
- `GET /api/mappings/{supplier_id}` → return mappings for a supplier
- `POST /api/mappings/{supplier_name}` → save supplier mappings
- `DELETE /api/suppliers/{supplier_id}` → delete a supplier and its mappings
- `POST /setup` → run interactive configuration setup
- `GET /files/{file_path}` → download a file
- `GET /api/schema` → return schema metadata for the default table
- `POST /api/parse-sample` → parse a small preview from an uploaded CSV/Excel file
- `POST /api/schema/check` → manually trigger schema drift detection
- `GET /api/schema/change-log` → return recent schema change log entries

## Database Schema

### Local SQLite database

The local application database is created automatically at startup via SQLAlchemy metadata.

#### `suppliers`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `name VARCHAR(100) UNIQUE NOT NULL`
- `source_fields JSON NULL`
- `mappings JSON NULL`
- `created_at DATETIME`
- `updated_at DATETIME`
- `schema_changed_at DATETIME NULL`
- `schema_changed_flag BOOLEAN`

#### `schema_change_log`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `checked_at DATETIME`
- `added_fields JSON`
- `removed_fields JSON`
- `suppliers_synced INTEGER`
- `details VARCHAR(500) NULL`

#### `target_fields`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `table_name VARCHAR(100) NOT NULL`
- `field_name VARCHAR(100) NOT NULL`
- `data_type VARCHAR(50) NULL`
- `max_length INTEGER NULL`
- `is_nullable BOOLEAN`
- `is_identity BOOLEAN`
- `default_value VARCHAR(255) NULL`
- `discovered_at DATETIME`
- `updated_at DATETIME`

Constraint:

- unique constraint on `(table_name, field_name)`

#### `import_audit`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `supplier_name VARCHAR(100) NOT NULL`
- `file_name VARCHAR(255) NOT NULL`
- `file_path VARCHAR(500) NOT NULL`
- `table_name VARCHAR(100) NOT NULL`
- `rows_processed INTEGER`
- `rows_succeeded INTEGER`
- `rows_failed INTEGER`
- `rows_skipped INTEGER`
- `status VARCHAR(20) NOT NULL`
- `error_message TEXT NULL`
- `dry_run BOOLEAN`
- `started_at DATETIME NOT NULL`
- `completed_at DATETIME NULL`
- `details JSON NULL`

Constraint:

- unique constraint on `(supplier_name, file_name, started_at)`

#### `import_settings`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `key VARCHAR(100) UNIQUE NOT NULL`
- `value TEXT NOT NULL`
- `description VARCHAR(500) NULL`
- `is_encrypted BOOLEAN`
- `created_at DATETIME`
- `updated_at DATETIME`

### Remote MSSQL source schema

The repository includes a schema excerpt in `src/db_queries.sql` for the source/target MyFactory table. The table shown there is `tdProducts_new`, with many product-related columns such as:

- `ProductID INT IDENTITY(1,1) NOT NULL`
- `ProductNumber NVARCHAR(30) NOT NULL`
- `Matchcode NVARCHAR(100) NULL`
- `BaseUnit NVARCHAR(10) NULL`
- `Name1 NVARCHAR(100) NULL`
- `Stock MONEY NULL`
- `IntraZollEAN NVARCHAR(10) NULL`
- `IntraCommodityID INT NULL`
- `IntraCommodityDescription NVARCHAR(200) NULL`
- `IntraDeclarationCurrency NVARCHAR(3) NULL`
- `SalesMinQuantity MONEY NULL`

The SQL file also shows default constraints and a foreign key to `tdProductTypes`.

## Appendix: Runtime Notes

- Local logging is JSON-formatted to rotating files under the log directory.
- The importer supports dry-run mode and records results in `ImportAudit`.
- Schema drift detection is best-effort; if MSSQL is unavailable, it fails gracefully and logs the issue.
- The application currently behaves as an internal tool with no web auth layer.
- The current import/mapping flow is designed around supplier-specific mappings stored in SQLite and applied to uploaded files before MSSQL insert.
