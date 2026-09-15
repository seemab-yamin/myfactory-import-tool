"""Schema scanner for Myfactory database tables.
Provides simplified schema information for the mapping UI.

SQLite persistence (TargetField table) is the single source of truth.
No in-process Python cache — avoids stale data across processes.
"""

from typing import Any, Dict, List, Optional

from src.db import get_db_manager, local_session
from src.logger import get_logger
from src.models import TargetField

logger = get_logger(__name__)


class SchemaScanner:
    """Scanner for database schema information."""

    def __init__(self):
        self.db = get_db_manager()

    def get_table_schema(
        self,
        table_name: str = "tdProducts",
        use_cache: bool = True,
        sort_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get full schema information for a table.

        Args:
            table_name: Table to scan
            use_cache:  If True, read from SQLite (TargetField). If False, read live from MSSQL.
            sort_by:    Optional key to sort by

        Returns:
            List of column dicts
        """

        try:
            columns = self.db.get_table_columns(table_name, use_cache)
            if not columns:
                return []

            if sort_by and sort_by in columns[0]:
                columns.sort(key=lambda x: x[sort_by])

            logger.info(f"Scanned {len(columns)} columns from {table_name}")
            return columns
        except Exception as e:
            logger.error(f"Failed to scan schema for {table_name}: {e}")
            return []

    def get_live_schema_as_target_fields(
        self,
        table_name: str = "tdProducts",
    ) -> List[TargetField]:
        """
        Fetch live schema from MSSQL as TargetField objects.

        Read-only: does NOT write to SQLite.

        Returns [] on failure so callers can short-circuit gracefully.
        """

        try:
            raw_columns = self.db.get_live_columns_from_mssql(table_name)
            if not raw_columns:
                logger.warning(f"No live columns returned for {table_name}")
                return []

            return [
                TargetField(
                    table_name=table_name,
                    field_name=col["name"],
                    data_type=col["type"],
                    max_length=col.get("max_length"),
                    is_nullable=col.get("nullable", True),
                    is_identity=col.get("is_identity", False),
                    default_value=col.get("default"),
                )
                for col in raw_columns
            ]
        except Exception as e:
            logger.error(f"Failed to fetch live {table_name} schema: {e}")
            return []

    def get_column_types(self, table_name: str = "tdProducts") -> Dict[str, str]:
        """Get mapping of column name -> data type."""
        columns = self.get_table_schema(table_name)
        return {col.get("name", ""): col.get("type", "") for col in columns}

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        return self.db.table_exists(table_name)

    def get_schema_summary(self, table_name: str = "tdProducts") -> Dict[str, Any]:
        """Get a summary of the table schema."""
        columns = self.get_table_schema(table_name)

        if not columns:
            return {
                "table_name": table_name,
                "exists": False,
                "total_columns": 0,
                "columns": [],
            }

        return {
            "table_name": table_name,
            "exists": True,
            "total_columns": len(columns),
            "columns": [
                {
                    "name": col.get("name"),
                    "type": col.get("type"),
                    "nullable": col.get("nullable", True),
                }
                for col in columns
            ],
        }


# ========== Singleton Accessor ==========

_scanner: Optional[SchemaScanner] = None


def get_scanner() -> SchemaScanner:
    """Get the global schema scanner instance."""
    global _scanner
    if _scanner is None:
        _scanner = SchemaScanner()
    return _scanner


# ========== Convenience Functions ==========


def get_table_schema(table_name: str = "tdProducts") -> List[Dict[str, Any]]:
    return get_scanner().get_table_schema(table_name)


def get_live_schema_as_target_fields(
    table_name: str = "tdProducts",
) -> List[TargetField]:
    return get_scanner().get_live_schema_as_target_fields(table_name)


def compare_schemas(
    cached_fields: List[TargetField], live_fields: List[TargetField]
) -> dict:
    """
    Compare cached (SQLite) vs live (MSSQL) schema for a table.

    Detects:
        1. Field name     → added / removed
        2. max_length     → narrowed (silent truncation risk)
        3. is_identity    → flipped (insert breaks)
        4. is_nullable    → escalated (NULL → NOT NULL, row-level failures)
        5. data_type      → narrowed (type conversion loss)
    """

    cached_by_name = {f.field_name: f for f in cached_fields}
    live_by_name = {f.field_name: f for f in live_fields}

    cached_names = set(cached_by_name.keys())
    live_names = set(live_by_name.keys())

    added = [live_by_name[n] for n in (live_names - cached_names)]
    removed = [cached_by_name[n] for n in (cached_names - live_names)]

    changed = []
    for name in cached_names & live_names:
        old = cached_by_name[name]
        new = live_by_name[name]
        diffs = {}

        if _is_length_narrowed(old.max_length, new.max_length):
            diffs["max_length"] = {"old": old.max_length, "new": new.max_length}

        if old.is_identity != new.is_identity:
            diffs["is_identity"] = {"old": old.is_identity, "new": new.is_identity}

        if old.is_nullable and not new.is_nullable:
            diffs["is_nullable"] = {"old": old.is_nullable, "new": new.is_nullable}

        if _is_type_narrowed(old.data_type, new.data_type):
            diffs["data_type"] = {"old": old.data_type, "new": new.data_type}

        if diffs:
            changed.append({"field_name": name, "changes": diffs})

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "has_changes": bool(added or removed or changed),
    }


# ============================================================
# HELPERS
# ============================================================


def _is_length_narrowed(old_len: Optional[int], new_len: Optional[int]) -> bool:
    """Return True only if the new max_length is strictly smaller than old."""
    if old_len is None or new_len is None:
        return False
    return new_len < old_len


def _is_type_narrowed(old_type: Optional[str], new_type: Optional[str]) -> bool:
    """Return True if the new data_type is strictly narrower than old."""

    if not old_type or not new_type:
        return False

    old_base = _base_type(old_type)
    new_base = _base_type(new_type)

    if old_base == new_base:
        return False

    numeric_rank = {
        "BIGINT": 4,
        "INTEGER": 3,
        "INT": 3,
        "SMALLINT": 2,
        "TINYINT": 1,
    }
    if old_base in numeric_rank and new_base in numeric_rank:
        return numeric_rank[new_base] < numeric_rank[old_base]

    string_family = {"NVARCHAR", "VARCHAR", "NCHAR", "CHAR", "TEXT", "NTEXT"}
    if old_base in string_family and new_base in string_family:
        return old_base != new_base

    datetime_family = {"DATETIME", "DATETIME2", "SMALLDATETIME", "DATE"}
    if old_base in datetime_family and new_base in datetime_family:
        return old_base != new_base

    return True


def _base_type(data_type: str) -> str:
    """Extract base type, e.g. 'NVARCHAR(30) COLLATE ...' → 'NVARCHAR'."""

    return data_type.split("(")[0].split()[0].strip().upper()


def detect_and_log_schema_changes(
    table_name: str = "tdProducts",
    apply_sync: bool = True,
) -> dict:
    """
    Thin wrapper around SchemaDriftService.check_and_sync().
    Kept for backward compatibility with existing callers.
    """

    from src.services.schema_drift_service import SchemaDriftService

    with local_session() as session:
        service = SchemaDriftService(
            db_session=session,
            table_name=table_name,
            apply_sync=apply_sync,
        )
        return service.check_and_sync()
