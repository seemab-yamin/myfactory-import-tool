"""Dynamic field mapping for Myfactory import with CRUD operations."""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.db import local_session
from src.logger import get_logger
from src.models import MappingConfig

logger = get_logger(__name__)


class FieldMapper:
    """
    Handles CSV to Myfactory field mapping with CRUD operations.

    Example:
        mapper = FieldMapper()

        # Save mappings
        mapper.save_mappings("supplier_a", {"SKU": "ProductID", "Name": "Description"})

        # Get mappings
        mappings = mapper.get_mappings("supplier_a")

        # Apply mapping
        df_mapped = mapper.apply_mapping(df, mappings)
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, str]] = {}

    # ========== CRUD Operations ==========

    def get_mappings(
        self, supplier_name: str, active_only: bool = True
    ) -> Dict[str, str]:
        """
        Get all mappings for a supplier.

        Args:
            supplier_name: Name of the supplier
            active_only: Only return active mappings

        Returns:
            Dictionary mapping source_field -> target_field
        """
        # Check cache first
        cache_key = f"{supplier_name}_{active_only}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        with local_session() as session:
            query = session.query(MappingConfig).filter(
                MappingConfig.supplier_name == supplier_name
            )

            if active_only:
                query = query.filter(MappingConfig.is_active == True)

            mappings = query.all()

            result = {m.source_field: m.target_field for m in mappings}
            self._cache[cache_key] = result

            logger.debug(
                f"Loaded {len(result)} mappings for supplier '{supplier_name}'"
            )
            return result

    def get_mapping_by_source(
        self, supplier_name: str, source_field: str
    ) -> Optional[str]:
        """
        Get target field for a specific source field.

        Args:
            supplier_name: Name of the supplier
            source_field: Source field name

        Returns:
            Target field name or None if not found
        """
        mappings = self.get_mappings(supplier_name)
        return mappings.get(source_field)

    def save_mapping(
        self,
        supplier_name: str,
        source_field: str,
        target_field: str,
        is_active: bool = True,
    ) -> MappingConfig:
        """
        Save a single mapping.

        Args:
            supplier_name: Name of the supplier
            source_field: Source field name (from CSV)
            target_field: Target field name (database column)
            is_active: Whether this mapping is active

        Returns:
            Created/updated MappingConfig instance
        """
        with local_session() as session:
            # Check if mapping exists
            existing = (
                session.query(MappingConfig)
                .filter(
                    MappingConfig.supplier_name == supplier_name,
                    MappingConfig.source_field == source_field,
                )
                .first()
            )

            if existing:
                existing.target_field = target_field
                existing.is_active = is_active
                mapping = existing
                logger.info(f"Updated mapping: {source_field} -> {target_field}")
            else:
                mapping = MappingConfig(
                    supplier_name=supplier_name,
                    source_field=source_field,
                    target_field=target_field,
                    is_active=is_active,
                )
                session.add(mapping)
                logger.info(f"Created mapping: {source_field} -> {target_field}")

            session.commit()

            # Clear cache
            self._cache.clear()

            return mapping

    def save_mappings(
        self, supplier_name: str, mappings: Dict[str, str], clear_existing: bool = True
    ) -> int:
        """
        Save multiple mappings.

        Args:
            supplier_name: Name of the supplier
            mappings: Dictionary mapping source_field -> target_field
            clear_existing: If True, delete all existing mappings for this supplier

        Returns:
            Number of mappings saved
        """
        with local_session() as session:
            if clear_existing:
                deleted = (
                    session.query(MappingConfig)
                    .filter(MappingConfig.supplier_name == supplier_name)
                    .delete()
                )
                logger.debug(
                    f"Deleted {deleted} existing mappings for '{supplier_name}'"
                )

            count = 0
            for source_field, target_field in mappings.items():
                if target_field:  # Skip empty mappings
                    mapping = MappingConfig(
                        supplier_name=supplier_name,
                        source_field=source_field,
                        target_field=target_field,
                        is_active=True,
                    )
                    session.add(mapping)
                    count += 1

            session.commit()

            # Clear cache
            self._cache.clear()

            logger.info(f"Saved {count} mappings for supplier '{supplier_name}'")
            return count

    def delete_mappings(self, supplier_name: str) -> int:
        """
        Delete all mappings for a supplier.

        Args:
            supplier_name: Name of the supplier

        Returns:
            Number of mappings deleted
        """
        with local_session() as session:
            deleted = (
                session.query(MappingConfig)
                .filter(MappingConfig.supplier_name == supplier_name)
                .delete()
            )
            session.commit()

            # Clear cache
            self._cache.clear()

            logger.info(f"Deleted {deleted} mappings for supplier '{supplier_name}'")
            return deleted

    def delete_mapping(self, supplier_name: str, source_field: str) -> bool:
        """
        Delete a specific mapping.

        Args:
            supplier_name: Name of the supplier
            source_field: Source field to delete

        Returns:
            True if deleted, False if not found
        """
        with local_session() as session:
            mapping = (
                session.query(MappingConfig)
                .filter(
                    MappingConfig.supplier_name == supplier_name,
                    MappingConfig.source_field == source_field,
                )
                .first()
            )

            if mapping:
                session.delete(mapping)
                session.commit()
                self._cache.clear()
                logger.info(f"Deleted mapping: {source_field} for '{supplier_name}'")
                return True

            logger.warning(f"Mapping not found: {source_field} for '{supplier_name}'")
            return False

    def toggle_mapping(self, supplier_name: str, source_field: str) -> bool:
        """
        Toggle active status of a mapping.

        Args:
            supplier_name: Name of the supplier
            source_field: Source field to toggle

        Returns:
            New active status
        """
        with local_session() as session:
            mapping = (
                session.query(MappingConfig)
                .filter(
                    MappingConfig.supplier_name == supplier_name,
                    MappingConfig.source_field == source_field,
                )
                .first()
            )

            if mapping:
                mapping.is_active = not mapping.is_active
                session.commit()
                self._cache.clear()
                logger.info(
                    f"Toggled mapping: {source_field} -> active={mapping.is_active}"
                )
                return mapping.is_active

            logger.warning(f"Mapping not found: {source_field} for '{supplier_name}'")
            return False

    def get_all_suppliers(self) -> List[str]:
        """Get list of all supplier names with mappings."""
        with local_session() as session:
            suppliers = session.query(MappingConfig.supplier_name).distinct().all()
            return [s[0] for s in suppliers]

    def get_mapping_summary(self, supplier_name: str) -> Dict[str, Any]:
        """
        Get summary of mappings for a supplier.

        Returns:
            Dict with count, active_count, inactive_count, mappings
        """
        with local_session() as session:
            all_mappings = (
                session.query(MappingConfig)
                .filter(MappingConfig.supplier_name == supplier_name)
                .all()
            )

            active = [m for m in all_mappings if m.is_active]
            inactive = [m for m in all_mappings if not m.is_active]

            return {
                "supplier_name": supplier_name,
                "total": len(all_mappings),
                "active": len(active),
                "inactive": len(inactive),
                "mappings": [m.to_dict() for m in all_mappings],
            }

    # ========== Mapping Application ==========

    def apply_mapping(
        self, df: pd.DataFrame, mapping: Dict[str, str], strict: bool = False
    ) -> pd.DataFrame:
        """
        Apply mapping to a DataFrame.

        Args:
            df: Input DataFrame
            mapping: Dictionary mapping source_field -> target_field
            strict: If True, raise error on missing columns

        Returns:
            Mapped DataFrame

        Raises:
            ValueError: If strict mode and columns are missing
        """

        if df.empty:
            logger.warning("DataFrame is empty")
            return df

        # Create new DataFrame with mapped columns
        mapped_data = {}
        unmapped_columns = []
        missing_columns = []

        for source_field, target_field in mapping.items():
            if source_field in df.columns:
                mapped_data[target_field] = df[source_field]
                logger.debug(f"Mapped '{source_field}' → '{target_field}'")
            else:
                missing_columns.append(source_field)
                logger.warning(f"Source column '{source_field}' not found in file")

        if strict and missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        # Create DataFrame from mapped data
        result_df = pd.DataFrame(mapped_data)

        # Log results
        logger.info(
            f"Mapped {len(mapped_data)} columns, {len(missing_columns)} unmapped"
        )

        return result_df

    def preview_mapping(self, df: pd.DataFrame, mapping: Dict[str, str]) -> None:
        """
        Preview the mapping for dry-run.

        Args:
            df: Input DataFrame
            mapping: Dictionary mapping source_field -> target_field
        """
        logger.info("=" * 50)
        logger.info("MAPPING PREVIEW")
        logger.info("=" * 50)

        logger.info(f"CSV Columns ({len(df.columns)}): {list(df.columns)}")
        logger.info(f"Mapping ({len(mapping)}): {mapping}")

        # Show which columns will be mapped
        mapped_cols = [col for col in mapping.keys() if col in df.columns]
        missing_cols = [col for col in mapping.keys() if col not in df.columns]

        logger.info(f"Found columns: {len(mapped_cols)}")
        logger.info(f"Missing columns: {len(missing_cols)}")
        if missing_cols:
            logger.warning(f"Missing: {missing_cols}")

        if not df.empty:
            logger.info("\nFirst 3 rows preview:")
            print(df.head(3).to_string())

        logger.info("=" * 50)

    # ========== Auto-Detection ==========

    def detect_mapping_suggestions(
        self,
        df: pd.DataFrame,
        target_columns: List[str],
        similarity_threshold: float = 0.6,
    ) -> Dict[str, str]:
        """
        Auto-detect mapping suggestions based on column name similarity.

        Args:
            df: Input DataFrame
            target_columns: List of target column names
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            Dictionary mapping source_field -> suggested_target
        """
        if df.empty:
            return {}

        source_columns = list(df.columns)
        suggestions = {}

        for source_col in source_columns:
            # Exact match
            if source_col in target_columns:
                suggestions[source_col] = source_col
                continue

            # Case-insensitive match
            lower_source = source_col.lower()
            lower_targets = {c.lower(): c for c in target_columns}

            if lower_source in lower_targets:
                suggestions[source_col] = lower_targets[lower_source]
                continue

            # Partial match (contains)
            for target_col in target_columns:
                if (
                    source_col.lower() in target_col.lower()
                    or target_col.lower() in source_col.lower()
                ):
                    suggestions[source_col] = target_col
                    break

            # Fuzzy/close match (Levenshtein-like)
            # This is a simplified version; you can use fuzzywuzzy for better matching
            if source_col not in suggestions:
                for target_col in target_columns:
                    if (
                        self._similarity_score(source_col, target_col)
                        >= similarity_threshold
                    ):
                        suggestions[source_col] = target_col
                        break

        logger.info(f"Auto-detected {len(suggestions)} mapping suggestions")
        return suggestions

    def _similarity_score(self, s1: str, s2: str) -> float:
        """Calculate simple similarity score between two strings."""
        s1 = s1.lower().strip()
        s2 = s2.lower().strip()

        if s1 == s2:
            return 1.0

        # Common substring ratio
        if s1 in s2 or s2 in s1:
            return 0.8

        # Character overlap
        common = len(set(s1) & set(s2))
        max_len = max(len(s1), len(s2))
        if max_len > 0:
            return common / max_len

        return 0.0

    # ========== Utility Methods ==========

    def clear_cache(self) -> None:
        """Clear the mapping cache."""
        self._cache.clear()
        logger.debug("Mapping cache cleared")

    def get_inverse_mapping(self, supplier_name: str) -> Dict[str, str]:
        """
        Get inverse mapping (target_field -> source_field).

        Args:
            supplier_name: Name of the supplier

        Returns:
            Dictionary mapping target_field -> source_field
        """
        mappings = self.get_mappings(supplier_name)
        return {v: k for k, v in mappings.items()}

    def validate_mapping(
        self, df: pd.DataFrame, mapping: Dict[str, str]
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate a mapping against a DataFrame.

        Args:
            df: Input DataFrame
            mapping: Dictionary mapping source_field -> target_field

        Returns:
            Tuple of (is_valid, missing_columns, mapped_columns)
        """
        missing_columns = [col for col in mapping.keys() if col not in df.columns]
        mapped_columns = [col for col in mapping.keys() if col in df.columns]
        is_valid = len(missing_columns) == 0

        if missing_columns:
            logger.warning(f"Missing columns for mapping: {missing_columns}")

        return is_valid, missing_columns, mapped_columns


# ========== Singleton Accessor ==========

_mapper: Optional[FieldMapper] = None


def get_mapper() -> FieldMapper:
    """Get the global mapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = FieldMapper()
    return _mapper


# ========== Example Usage ==========
if __name__ == "__main__":
    mapper = get_mapper()

    # Save mappings
    mapper.save_mappings(
        "supplier_a",
        {
            "SKU": "ProductID",
            "Name": "Description",
            "Price": "Price",
            "Category": "ProductGroup",
        },
    )

    # Get mappings
    mappings = mapper.get_mappings("supplier_a")
    print(f"Mappings for supplier_a: {mappings}")

    # Get summary
    summary = mapper.get_mapping_summary("supplier_a")
    print(f"Summary: {summary}")

    # Get all suppliers
    suppliers = mapper.get_all_suppliers()
    print(f"All suppliers: {suppliers}")
