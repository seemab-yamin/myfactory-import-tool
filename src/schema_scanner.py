"""Schema scanner for Myfactory database tables.
Provides simplified schema information for the mapping UI.
"""

from typing import Any, Dict, List, Optional

from src.db import get_db_manager
from src.logger import get_logger

logger = get_logger(__name__)


class SchemaScanner:
    """Scanner for database schema information."""

    def __init__(self):
        self.db = get_db_manager()
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    def get_table_schema(
        self, table_name: str = "tdProducts", use_cache: bool = True
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
        if use_cache and cache_key in self._cache:
            logger.debug(f"Returning cached schema for {table_name}")
            return self._cache[cache_key]

        try:
            columns = self.db.get_table_columns(table_name, use_cache)
            self._cache[cache_key] = columns
            logger.info(f"Scanned {len(columns)} columns from {table_name}")
            return columns
        except Exception as e:
            logger.error(f"Failed to scan schema for {table_name}: {e}")
            return []

    def get_columns_for_mapping(
        self, table_name: str = "tdProducts", use_cache: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get simplified column list for mapping UI.

        Returns:
            List of dicts with 'name' and 'type' only.
            Example: [{"name": "ProductNumber", "type": "varchar"}, ...]
        """

        columns = self.get_table_schema(table_name, use_cache)
        return [
            {
                "name": col.get("name", ""),
                "type": col.get("type", "unknown"),
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


# ========== Example Usage ==========
if __name__ == "__main__":
    scanner = get_scanner()

    # Get full schema
    schema = scanner.get_table_schema("tdProducts")
    print(f"Found {len(schema)} columns")
    if schema:
        print(f"First column: {schema[0]}")

    # Get simplified for mapping
    mapping_columns = scanner.get_columns_for_mapping("tdProducts")
    print(f"Mapping columns: {mapping_columns[:5]}...")

    # Get summary
    summary = scanner.get_schema_summary("tdProducts")
    print(f"Summary: {summary}")
