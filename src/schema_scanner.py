"""Schema scanner for Myfactory database tables.
Provides simplified schema information for the mapping UI.
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
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    def get_table_schema(
        self,
        table_name: str = "tdProducts",
        use_cache: bool = True,
        sort_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get full schema information for a table.

        Args:
            table_name: Name of the table to scan
            use_cache: Use cached columns if available

        Returns:
            List of column dictionaries
        """

        cache_key = f"schema_{table_name}"
        if use_cache and cache_key in self._cache and sort_by is None:
            logger.debug(f"Returning cached schema for {table_name}")
            return self._cache[cache_key]

        try:
            columns = self.db.get_table_columns(table_name, use_cache)
            if sort_by and columns and sort_by in columns[0]:
                columns.sort(key=lambda x: x[sort_by])

            if sort_by in columns[0]:
                columns.sort(key=lambda x: x[sort_by])
            self._cache[cache_key] = columns
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
        Fetch live schema from MSSQL, bypassing cache, as TargetField objects.

        Read-only: does NOT write to SQLite cache.
        Returns [] on failure so callers can short-circuit gracefully.
        """

        try:
            raw_columns = self.db.get_table_columns(table_name, use_cache=False)
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
                    is_identity=col.get("identity", False),
                    default_value=col.get("default"),
                )
                for col in raw_columns
            ]
        except Exception as e:
            logger.error(f"Failed to fetch live {table_name} schema: {e}")
            return []

    def get_columns_for_mapping(
        self,
        table_name: str = "tdProducts",
        use_cache: bool = True,
        sort_by: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Get simplified column list for mapping UI.

        Returns:
            List of dicts with 'name' and 'type' only.
            Example: [{"name": "ProductNumber", "type": "varchar"}, ...]
        """

        columns = self.get_table_schema(table_name, use_cache, sort_by=sort_by)
        return [
            {
                "name": col["name"],
                "type": col["type"],
            }
            for col in columns
        ]

    def get_column_names(
        self, table_name: str = "tdProducts", use_cache: bool = True
    ) -> List[str]:
        """Get just the column names."""
        columns = self.get_table_schema(table_name, use_cache)
        return [col.get("name", "") for col in columns if col.get("name")]

    def get_column_types(self, table_name: str = "tdProducts") -> Dict[str, str]:
        """Get mapping of column name -> data type."""
        columns = self.get_table_schema(table_name)
        return {col.get("name", ""): col.get("type", "") for col in columns}

    def refresh_cache(self, table_name: Optional[str] = None):
        """
        Refresh cached schema for a table or all tables.
        """

        if table_name:
            cache_key = f"schema_{table_name}"
            if cache_key in self._cache:
                del self._cache[cache_key]
            self.get_table_schema(table_name, use_cache=False)
            logger.info(f"Cache refreshed for {table_name}")
        else:
            self._cache.clear()
            logger.info("All schema caches cleared")

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
    """Get schema for a table."""
    return get_scanner().get_table_schema(table_name)


def get_columns_for_mapping(table_name: str = "tdProducts") -> List[Dict[str, str]]:
    """Get simplified columns for mapping UI."""
    return get_scanner().get_columns_for_mapping(table_name)


def get_column_names(table_name: str = "tdProducts") -> List[str]:
    """Get column names for a table."""
    return get_scanner().get_column_names(table_name)


def refresh_schema_cache(table_name: Optional[str] = None):
    """Refresh the schema cache."""
    return get_scanner().refresh_cache(table_name)


def get_live_schema_as_target_fields(
    table_name: str = "tdProducts",
) -> List[TargetField]:
    """Get live schema as TargetField objects."""
    return get_scanner().get_live_schema_as_target_fields(table_name)


def compare_schemas(
    cached_fields: List[TargetField], live_fields: List[TargetField]
) -> dict:
    """
    Compare cached vs live schema for tdProducts.

    Detects:
        1. Field name           → added / removed
        2. max_length           → narrowed (silent truncation risk)
        3. is_identity          → flipped (insert breaks)
        4. is_nullable          → escalated (NULL → NOT NULL, row-level failures)
        5. data_type            → narrowed (type conversion loss)

    Returns:
        {
            "added":        [TargetField, ...],   # new in live
            "removed":      [TargetField, ...],   # gone from live
            "changed":      [dict, ...],          # same name, different metadata
            "has_changes":  bool,
        }
    """
    cached_by_name = {f.field_name: f for f in cached_fields}
    live_by_name = {f.field_name: f for f in live_fields}

    cached_names = set(cached_by_name.keys())
    live_names = set(live_by_name.keys())

    # ---- 1. Field presence diff ----
    added = [live_by_name[n] for n in (live_names - cached_names)]
    removed = [cached_by_name[n] for n in (cached_names - live_names)]

    # ---- 2–5. Metadata diff on common fields ----
    changed = []
    for name in cached_names & live_names:
        old = cached_by_name[name]
        new = live_by_name[name]

        diffs = {}

        # 2. max_length narrowed (e.g., 100 → 30)
        if _is_length_narrowed(old.max_length, new.max_length):
            diffs["max_length"] = {"old": old.max_length, "new": new.max_length}

        # 3. is_identity flipped (True → False breaks inserts)
        if old.is_identity != new.is_identity:
            diffs["is_identity"] = {"old": old.is_identity, "new": new.is_identity}

        # 4. Nullability escalated (nullable=True → False)
        if old.is_nullable and not new.is_nullable:
            diffs["is_nullable"] = {"old": old.is_nullable, "new": new.is_nullable}

        # 5. Type narrowed (e.g., NVARCHAR(30) → NVARCHAR(10), INT → SMALLINT)
        if _is_type_narrowed(old.data_type, new.data_type):
            diffs["data_type"] = {"old": old.data_type, "new": new.data_type}

        if diffs:
            changed.append(
                {
                    "field_name": name,
                    "changes": diffs,
                }
            )
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
    """
    Return True if the new data_type is strictly narrower than old.

    Narrowing rules:
        - Same base type, smaller length (handled by _is_length_narrowed too,
          but catches cases where only data_type string changes)
        - Numeric rank: BIGINT > INT > SMALLINT > TINYINT
        - String rank:  NVARCHAR > VARCHAR (length tracked separately)
        - Any change where new_type is NOT a superset of old_type
    """
    if not old_type or not new_type:
        return False

    old_base = _base_type(old_type)
    new_base = _base_type(new_type)

    if old_base == new_base:
        return False  # Same base — length handled elsewhere

    # Numeric narrowing: rank order matters
    numeric_rank = {
        "BIGINT": 4,
        "INTEGER": 3,
        "INT": 3,
        "SMALLINT": 2,
        "TINYINT": 1,
    }
    if old_base in numeric_rank and new_base in numeric_rank:
        return numeric_rank[new_base] < numeric_rank[old_base]

    # String narrowing: NVARCHAR → VARCHAR is fine (same capacity),
    # but VARCHAR → NVARCHAR on non-ASCII data is a risk.
    # Treat any base-type change between string families as narrowing.
    string_family = {"NVARCHAR", "VARCHAR", "NCHAR", "CHAR", "TEXT", "NTEXT"}
    if old_base in string_family and new_base in string_family:
        return old_base != new_base

    # Date/time family
    datetime_family = {"DATETIME", "DATETIME2", "SMALLDATETIME", "DATE"}
    if old_base in datetime_family and new_base in datetime_family:
        return old_base != new_base

    # Unknown change — flag as narrowing to be safe
    return True


def _base_type(data_type: str) -> str:
    """Extract base type from full type string, e.g. 'NVARCHAR(30) COLLATE ...' → 'NVARCHAR'."""
    return data_type.split("(")[0].split()[0].strip().upper()


def detect_and_log_schema_changes(
    table_name: str = "tdProducts",
    apply_sync: bool = True,
) -> dict:
    """
    Thin wrapper around SchemaDriftService.check_and_sync().

    Kept for backward compatibility with existing callers
    (API routes, tests). New code should use SchemaDriftService directly.
    """

    from src.services.schema_drift_service import SchemaDriftService

    with local_session() as session:
        service = SchemaDriftService(
            db_session=session,
            table_name=table_name,
            apply_sync=apply_sync,
        )
        return service.check_and_sync()
