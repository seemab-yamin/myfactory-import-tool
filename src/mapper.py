"""Dynamic field mapping for Myfactory import with CRUD operations."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.db import local_session
from src.logger import get_logger
from src.models import MappingConfig, Supplier, TargetField

logger = get_logger(__name__)


class FieldMapper:
    """
    Handles CSV to Myfactory field mapping with CRUD operations.

    Example:
        mapper = FieldMapper()

        # Get mappings
        mappings = mapper.get_mappings(1)

        # Apply mapping
        df_mapped = mapper.apply_mapping(df, mappings)
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, str]] = {}
        self._supplier_cache: Dict[str, Optional[int]] = {}

    # ========== CRUD Operations ==========
    def get_mappings(self, supplier_id: int, active_only: bool = True):
        """
        Get all mappings for a supplier with full details.

        Args:
            supplier_id: ID of the supplier
            active_only: Only return active mappings

        Returns:
            List of dictionaries with keys:
                - source_field: str
                - target_field: str (field name)
                - target_field_id: int
                - is_mandatory: bool
                - is_active: bool
                - prepopulated_value: str or None
        """

        # Check cache first
        cache_key = f"{supplier_id}_{active_only}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        with local_session() as session:
            query = session.query(MappingConfig).filter(
                MappingConfig.supplier_id == supplier_id
            )
            if active_only:
                query = query.filter(MappingConfig.is_active == True)

            # ✅ Build list of dicts with all fields
            mappings = []
            for m in query.all():
                mappings.append(
                    {
                        "source_field": m.source_field,
                        "target_field": (
                            m.target_field.field_name if m.target_field else None
                        ),
                        "target_field_id": m.target_field_id,
                        "is_mandatory": m.is_mandatory,
                        "is_active": m.is_active,
                        "prepopulated_value": m.prepopulated_value,
                    }
                )

            self._cache[cache_key] = mappings
            return mappings

    def mapping_name_exists(self, mapping_name: str) -> bool:
        """Check if a supplier has any mappings (lightweight with LIMIT 1)."""
        with local_session() as session:
            exists = (
                session.query(Supplier.id)
                .filter(Supplier.id == mapping_name)
                .limit(1)
                .first()
                is not None
            )
            return exists

    def save_mapping(
        self,
        supplier_name: str,
        source_field: str,
        target_field_id: int,
        is_active: bool = True,
        is_mandatory: bool = False,
        prepopulated_value: Optional[str] = None,
    ) -> Tuple[int, MappingConfig]:
        """
        Save a single mapping.

        Args:
            supplier_name: Name of the supplier (will be resolved to ID)
            source_field: Source field name (from CSV)
            target_field_id: ID of the target field (database column)
            is_active: Whether this mapping is active
            is_mandatory: Whether this field is required for import
            prepopulated_value: Optional value to prepopulate the target field

        Returns:
            Tuple of (supplier_id, MappingConfig) - the supplier ID and the created/updated mapping
        """

        # ✅ Resolve supplier name to ID (using cached helper)
        supplier_id = self._get_or_create_supplier(supplier_name)

        with local_session() as session:
            # ✅ Use supplier_id in the filter
            existing = (
                session.query(MappingConfig)
                .filter(
                    MappingConfig.supplier_id == supplier_id,
                    MappingConfig.target_field_id == target_field_id,
                )
                .first()
            )

            if existing:
                existing.source_field = source_field
                existing.target_field_id = target_field_id
                existing.is_active = is_active
                existing.is_mandatory = is_mandatory
                existing.prepopulated_value = prepopulated_value
                mapping = existing
                logger.info(f"Updated mapping: {source_field} -> {target_field_id}")
            else:
                mapping = MappingConfig(
                    supplier_id=supplier_id,
                    source_field=source_field,
                    target_field_id=target_field_id,
                    is_active=is_active,
                    is_mandatory=is_mandatory,
                    prepopulated_value=prepopulated_value,
                )
                session.add(mapping)
                logger.info(f"Created mapping: {source_field} -> {target_field_id}")

            session.commit()
            self._cache.clear()
            self._supplier_cache.clear()
            print(
                f"TODO: save_mapping({supplier_name}, {source_field}, {target_field_id}) -> {mapping}"
            )
            return supplier_id, mapping

    def delete_supplier(self, supplier_id: int) -> bool:
        """
        Delete a supplier and all its associated mappings.

        Args:
            supplier_id: ID of the supplier to delete

        Returns:
            True if deleted, False if supplier not found
        """

        with local_session() as session:
            # Check if supplier exists
            supplier = (
                session.query(Supplier).filter(Supplier.id == supplier_id).first()
            )
            if not supplier:
                logger.warning(f"Supplier with ID {supplier_id} not found")
                return False

            # ✅ Delete all mappings for this supplier first
            deleted_mappings = (
                session.query(MappingConfig)
                .filter(MappingConfig.supplier_id == supplier_id)
                .delete()
            )

            # ✅ Delete the supplier
            session.delete(supplier)
            session.commit()

            # Clear caches
            self._cache.clear()
            self._supplier_cache.clear()

            logger.info(
                f"Deleted supplier ID {supplier_id} with {deleted_mappings} mappings"
            )
            return True

    def delete_mappings(self, supplier_id: int) -> int:
        """
        Delete all mappings for a supplier.

        Args:
            supplier_id: ID of the supplier

        Returns:
            Number of mappings deleted
        """

        with local_session() as session:
            deleted = (
                session.query(MappingConfig)
                .filter(MappingConfig.supplier_id == supplier_id)  # ✅ Use supplier_id
                .delete()
            )
            session.commit()

            self._cache.clear()
            self._supplier_cache.clear()

            logger.info(f"Deleted {deleted} mappings for supplier '{supplier_id}'")
            return deleted

    def delete_mapping(self, supplier_id: int, source_field: str) -> bool:
        """
        Delete a specific mapping.

        Args:
            supplier_id: ID of the supplier
            source_field: Source field to delete

        Returns:
            True if deleted, False if not found
        """

        with local_session() as session:
            mapping = (
                session.query(MappingConfig)
                .filter(
                    MappingConfig.supplier_id == supplier_id,
                    MappingConfig.source_field == source_field,
                )
                .first()
            )

            if mapping:
                session.delete(mapping)
                session.commit()
                self._cache.clear()
                self._supplier_cache.clear()
                logger.info(f"Deleted mapping: {source_field} for '{supplier_id}'")
                return True

            logger.warning(f"Mapping not found: {source_field} for '{supplier_id}'")
            return False

    def get_all_suppliers(self) -> List[str]:
        """Get list of all supplier names with mappings."""
        with local_session() as session:
            # fetch supplier id and name from Supplier table, ordered by name
            suppliers = (
                session.query(Supplier.id, Supplier.name).order_by(Supplier.name).all()
            )
            suppliers = [(s.id, s.name) for s in suppliers]  # Convert to list of tuples
            return suppliers  # Return list of tuples (id, name) for better clarity

    def get_supplier_by_id(self, supplier_id: int) -> Optional[Dict[str, Any]]:
        """
        Get supplier details by ID.

        Args:
            supplier_id: ID of the supplier

        Returns:
            Supplier details as dict, or None if not found
        """
        with local_session() as session:
            supplier = (
                session.query(Supplier).filter(Supplier.id == supplier_id).first()
            )
            if not supplier:
                return None

            return {
                "id": supplier.id,
                "name": supplier.name,
                "source_fields": supplier.source_fields or [],
                "created_at": (
                    supplier.created_at.isoformat() if supplier.created_at else None
                ),
                "updated_at": (
                    supplier.updated_at.isoformat() if supplier.updated_at else None
                ),
            }

    def save_source_fields(self, supplier_id: int, source_fields: List[str]) -> bool:
        """
        Save the source fields (column headers) for a supplier.

        Args:
            supplier_id: ID of the supplier
            source_fields: List of column names from the uploaded file

        Returns:
            True if saved successfully, False if supplier not found
        """
        with local_session() as session:
            supplier = (
                session.query(Supplier).filter(Supplier.id == supplier_id).first()
            )
            if not supplier:
                logger.warning(f"Supplier with ID {supplier_id} not found")
                return False

            # ✅ Overwrite source_fields (replace, not merge)
            supplier.source_fields = source_fields
            supplier.updated_at = datetime.utcnow()
            session.commit()

            # Clear cache
            self._supplier_cache.clear()

            logger.info(
                f"Saved {len(source_fields)} source fields for supplier ID {supplier_id}"
            )
            return True

    def get_source_fields(self, supplier_id: int) -> Optional[List[str]]:
        """
        Get the source fields (column headers) for a supplier.

        Args:
            supplier_id: ID of the supplier

        Returns:
            List of column names, or None if supplier not found
        """
        with local_session() as session:
            supplier = (
                session.query(Supplier).filter(Supplier.id == supplier_id).first()
            )
            if not supplier:
                logger.warning(f"Supplier with ID {supplier_id} not found")
                return None

            return supplier.source_fields or []

    def get_target_fields(self) -> List[Dict[str, Any]]:
        """
        Get all available target fields from the target_fields table.

        Returns:
            List of target field dicts with id, field_name, data_type
        """
        with local_session() as session:
            target_fields = (
                session.query(TargetField).order_by(TargetField.field_name).all()
            )
            return [
                {
                    "id": tf.id,
                    "field_name": tf.field_name,
                    "data_type": tf.data_type,
                    "is_nullable": tf.is_nullable,
                }
                for tf in target_fields
            ]

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
        self._supplier_cache.clear()
        logger.debug("Mapping cache cleared")

    def get_inverse_mapping(self, supplier_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Get inverse mapping: target_field -> details dict.

        Args:
            supplier_id: ID of the supplier

        Returns:
            Dictionary mapping target_field -> {
                source_field: str,
                is_mandatory: bool,
                is_active: bool,
                prepopulated_value: str or None
            }
        """

        mappings = self.get_mappings(supplier_id, active_only=False)
        result = {}
        for m in mappings:
            target = m.get("target_field")
            if target:
                result[target] = {
                    "source_field": m.get("source_field"),
                    "is_mandatory": m.get("is_mandatory", False),
                    "is_active": m.get("is_active", True),
                    "prepopulated_value": m.get("prepopulated_value"),
                }
        return result

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

    # ========== New Methods (for backward compatibility) ==========

    def get_mappings_with_details(
        self, supplier_id: int, active_only: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all mappings for a supplier with full details.

        Args:
            supplier_id: ID of the supplier
            active_only: Only return active mappings

        Returns:
            Dictionary mapping target_field -> details
        """

        cache_key = f"details_{supplier_id}_{active_only}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        with local_session() as session:
            query = session.query(MappingConfig).filter(
                MappingConfig.supplier_id == supplier_id
            )

            if active_only:
                query = query.filter(MappingConfig.is_active == True)

            mappings = query.all()

            result = {}
            for m in mappings:
                target_field_name = (
                    m.target_field.field_name if m.target_field else None
                )
                result[target_field_name] = {
                    "source_field": m.source_field,
                    "is_mandatory": m.is_mandatory,
                    "is_active": m.is_active,
                    "prepopulated_value": m.prepopulated_value,
                }

            self._cache[cache_key] = result
            return result

    # ========== Helper Methods ==========

    def _get_supplier_id(self, supplier_name: str) -> Optional[int]:
        """Get supplier ID from name (with caching)."""
        if supplier_name in self._supplier_cache:
            return self._supplier_cache[supplier_name]
        with local_session() as session:
            supplier = (
                session.query(Supplier).filter(Supplier.name == supplier_name).first()
            )
            supplier_id = supplier.id if supplier else None
            self._supplier_cache[supplier_name] = supplier_id
            return supplier_id

    def _get_or_create_supplier(self, supplier_name: str) -> int:
        """Get supplier ID, or create a new supplier if it doesn't exist."""
        supplier_id = self._get_supplier_id(supplier_name)
        if supplier_id is not None:
            return supplier_id

        with local_session() as session:
            supplier = Supplier(name=supplier_name, source_fields=[])
            session.add(supplier)
            session.commit()
            self._supplier_cache[supplier_name] = supplier.id
            return supplier.id


# ========== Singleton Accessor ==========

_mapper: Optional[FieldMapper] = None


def get_mapper() -> FieldMapper:
    """Get the global mapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = FieldMapper()
    return _mapper
