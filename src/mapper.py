"""Dynamic field mapping for Myfactory import with CRUD operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.db import local_session
from src.logger import get_logger
from src.models import Supplier, TargetField

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
            query = session.query(Supplier).filter(Supplier.id == supplier_id)

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

    def save_mappings(
        self,
        supplier_name: str,
        source_fields: List[str],
        mappings: List[dict],
        is_new_supplier: bool = False,
    ):
        """
        Save mappings for a supplier.

        Args:
            supplier_name: Name of the supplier (will be resolved to ID)
            source_fields: List of source field names (from CSV)
            mappings: List of dictionaries with keys:
                - source_field: str
                - target_field: str (field name)
                - target_field_id: int
                - is_mandatory: bool
                - is_active: bool
                - prepopulated_value: str or None
        """
        # ✅ Normalize List[dict] → dict keyed by target_field_name
        mappings_dict = {
            m["target_field_name"]: m for m in mappings if m.get("target_field_name")
        }

        with local_session() as session:
            if is_new_supplier:

                sup = Supplier(
                    name=supplier_name,
                    source_fields=source_fields,
                    mappings=mappings_dict,
                )
                session.add(sup)
                session.flush()
                supplier_id = sup.id

                logger.info(
                    f"Created mapping: name={supplier_name}, "
                    f"source_fields={len(source_fields)}, "
                    f"mappings={len(mappings_dict)}"
                )
            else:
                # ✅ Use different variable names to avoid confusion
                existing = self._get_supplier_id(supplier_name)

                # ✅ Check if supplier exists
                if existing is None or existing[0] is None:
                    raise ValueError(f"Supplier '{supplier_name}' not found")

                # ✅ Unpack safely
                (
                    existing_id,
                    _,
                    _,
                    _,
                    _,
                    _,
                ) = existing

                # ✅ Get the supplier object for update
                sup = session.query(Supplier).filter(Supplier.id == existing_id).first()

                if sup is None:
                    raise ValueError(f"Supplier with ID {existing_id} not found")

                # ✅ Update fields
                sup.source_fields = source_fields
                sup.mappings = mappings_dict
                sup.updated_at = datetime.now(timezone.utc)
                supplier_id = sup.id  # Ensure supplier_id is set for return
                logger.info(
                    f"Updated mapping: name={supplier_name}, "
                    f"source_fields={len(source_fields)}, "
                    f"mappings={len(mappings_dict)}"
                )

            # ✅ Commit
            try:
                session.commit()
                # ✅ Refresh to verify
                session.refresh(sup)
            except Exception as e:
                session.rollback()
                raise e
            # ✅ Clear caches
            self._cache.clear()
            self._supplier_cache.clear()
            return sup, supplier_id

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
            session.query(Supplier).filter(Supplier.id == supplier_id).delete()
            # Delete all mappings for this supplier
            self._cache.clear()
            self._supplier_cache.clear()

            logger.info(f"Deleted supplier ID {supplier_id}")
            return True

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
                "mappings": supplier.mappings or {},  # ✅ dict fallback
                "created_at": (
                    supplier.created_at.isoformat() if supplier.created_at else None
                ),
                "updated_at": (
                    supplier.updated_at.isoformat() if supplier.updated_at else None
                ),
            }

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

    # ========== Utility Methods ==========

    def clear_cache(self) -> None:
        """Clear the mapping cache."""
        self._cache.clear()
        self._supplier_cache.clear()
        logger.debug("Mapping cache cleared")

    # ========== Helper Methods ==========

    def _get_supplier_id(self, supplier_name: str):
        """Get supplier by name."""

        with local_session() as session:
            sup = session.query(Supplier).filter(Supplier.name == supplier_name).first()

            if sup:
                return (
                    sup.id,
                    sup.name,
                    sup.updated_at,
                    sup.created_at,
                    sup.mappings,
                    sup.source_fields,
                )
            else:
                return None

    def _get_or_create_supplier(
        self, supplier_name: str, source_fields: List[str] = None
    ) -> Tuple[Supplier, int]:
        """Get supplier ID, or create a new supplier if it doesn't exist."""
        (
            supplier_id,
            name,
            updated_at,
            created_at,
            mappings,
            source_fields,
        ) = self._get_supplier_id(supplier_name)
        if supplier_id is not None:
            return (
                supplier_id,
                name,
                updated_at,
                created_at,
                mappings,
                source_fields,
            )

        with local_session() as session:
            sup = Supplier(name=supplier_name, source_fields=source_fields)
            session.add(sup)
            session.commit()
            self._supplier_cache[supplier_name] = sup.id
            return (
                sup.id,
                sup.name,
                sup.updated_at,
                sup.created_at,
                sup.mappings,
                sup.source_fields,
            )


# ========== Singleton Accessor ==========

_mapper: Optional[FieldMapper] = None


def get_mapper() -> FieldMapper:
    """Get the global mapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = FieldMapper()
    return _mapper


def sync_supplier_json(
    supplier: Supplier,
    schema_diff: dict,
) -> bool:
    """
    Reconcile a supplier's mappings with a schema diff.

    Removes mappings for target fields that no longer exist.
    Stamps schema_changed_flag/at if any mutation occurred.

    Returns:
        True if supplier.mappings was mutated, False otherwise.
    """
    # Short-circuit: no removals → nothing to do
    removed = schema_diff.get("removed", [])
    if not removed:
        return False

    removed_names = {f.field_name for f in removed}

    # Defensive copy — SQLAlchemy JSON needs explicit reassignment
    mappings = dict(supplier.mappings or {})

    mutated = False
    for name in removed_names:
        if name in mappings:
            del mappings[name]
            mutated = True

    if not mutated:
        return False

    # ✅ Explicit reassignment → triggers SQLAlchemy dirty-tracking
    supplier.mappings = mappings

    # ✅ Stamp once per drift event (idempotent guard)
    if not supplier.schema_changed_flag:
        supplier.schema_changed_at = datetime.now(timezone.utc)
        supplier.schema_changed_flag = True

    return True


def sync_all_suppliers(schema_diff: dict, db_session) -> int:
    """
    Apply a schema diff to all suppliers in a single transaction.

    - Short-circuits when no removals exist (nothing to mutate).
    - Calls sync_supplier_json() per supplier.
    - Commits once at the end → atomic batch.
    - Rolls back on any error.

    Args:
        schema_diff: Output from compare_schemas()
        db_session:  SQLAlchemy Session (caller-provided)

    Returns:
        Count of suppliers whose mappings were actually mutated.
    """
    # Short-circuit: no removals → no mapping mutation possible
    if not schema_diff.get("has_changes"):
        return 0
    if not schema_diff.get("removed"):
        return 0

    suppliers = db_session.query(Supplier).all()
    synced_count = 0

    try:
        for supplier in suppliers:
            if sync_supplier_json(supplier, schema_diff):
                synced_count += 1

        db_session.commit()
    except Exception:
        db_session.rollback()
        raise

    logger.info(
        f"sync_all_suppliers: {synced_count}/{len(suppliers)} suppliers mutated"
    )
    return synced_count
