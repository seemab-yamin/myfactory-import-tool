"""Schema scanner for Myfactory database tables.
Provides simplified schema information for the mapping UI.

SQLite persistence (TargetField table) is the single source of truth.
No in-process Python cache — avoids stale data across processes.
"""

from typing import Optional

from src.db import get_db_manager, local_session
from src.logger import get_logger
from src.models import TargetField

logger = get_logger(__name__)


class SchemaScanner:
    """Scanner for database schema information."""

    def __init__(self):
        self.db = get_db_manager()


# ========== Singleton Accessor ==========

_scanner: Optional[SchemaScanner] = None


def get_scanner() -> SchemaScanner:
    """Get the global schema scanner instance."""
    global _scanner
    if _scanner is None:
        _scanner = SchemaScanner()
    return _scanner


# ========== Convenience Functions ==========


def compare_schemas(
    cached_fields: list[TargetField], live_fields: list[TargetField]
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

        if _is_length_changed(old.max_length, new.max_length):
            diffs["max_length"] = {"old": old.max_length, "new": new.max_length}

        if old.is_identity != new.is_identity:
            diffs["is_identity"] = {"old": old.is_identity, "new": new.is_identity}

        if old.is_nullable and not new.is_nullable:
            diffs["is_nullable"] = {"old": old.is_nullable, "new": new.is_nullable}

        if _is_type_changed(old.data_type, new.data_type):
            diffs["data_type"] = {"old": old.data_type, "new": new.data_type}

        if diffs:
            changed.append(
                {
                    "field_name": name,
                    "old": old,
                    "new": new,
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


def _is_length_changed(old_len: Optional[int], new_len: Optional[int]) -> bool:
    """Return True if the new max_length is not equal to the old max_length."""
    if old_len is None or new_len is None:
        return False
    return new_len != old_len


def _is_type_changed(old_type: Optional[str], new_type: Optional[str]) -> bool:
    """
    Return True if the new data type is incompatible with the old data type.
    This includes cases where the types are fundamentally different or where
    a more restrictive type is introduced.

    """

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
    products_table: str = "tdProducts",
    attribute_values_table: str = "tdAttributeValues",
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
            products_table=products_table,
            attribute_values_table=attribute_values_table,
            apply_sync=apply_sync,
        )
        return service.check_and_sync()
