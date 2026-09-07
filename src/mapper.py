"""Dynamic field mapping for Myfactory import with CRUD operations."""

from datetime import datetime
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

        print("=" * 70)
        print("🔍 SAVE_MAPPINGS DEBUG START")
        print("=" * 70)
        print(f"📌 supplier_name: {supplier_name}")
        print(f"📌 is_new_supplier: {is_new_supplier}")
        print(f"📌 incoming source_fields: {source_fields}")
        print(
            f"📌 incoming source_fields count: {len(source_fields) if source_fields else 0}"
        )
        print(f"📌 incoming mappings count: {len(mappings) if mappings else 0}")

        if mappings and len(mappings) > 0:
            print(f"📌 First 3 incoming mappings: {mappings[:3]}")
        else:
            print("⚠️ incoming mappings is empty or None")
        print("=" * 70)

        with local_session() as session:
            if is_new_supplier:
                print("🔍 Creating NEW supplier...")

                sup = Supplier(
                    name=supplier_name,
                    source_fields=source_fields,
                    mappings=mappings,
                )
                session.add(sup)
                session.flush()
                supplier_id = sup.id

                print(f"✅ Created new supplier with ID: {supplier_id}")
                print(f"✅ Supplier name: {sup.name}")
                print(f"✅ source_fields: {sup.source_fields}")
                print(f"✅ mappings count: {len(sup.mappings) if sup.mappings else 0}")

                logger.info(
                    f"Created mapping: name={supplier_name}, "
                    f"source_fields={len(source_fields)}, "
                    f"mappings={len(mappings)}"
                )

            else:
                print("🔍 Updating EXISTING supplier...")
                print(f"🔍 Looking for supplier: {supplier_name}")

                # ✅ Use different variable names to avoid confusion
                existing = self._get_supplier_id(supplier_name)

                # ✅ Check if supplier exists
                if existing is None or existing[0] is None:
                    print(f"❌ Supplier '{supplier_name}' not found!")
                    raise ValueError(f"Supplier '{supplier_name}' not found")

                # ✅ Unpack safely
                (
                    existing_id,
                    existing_name,
                    existing_updated_at,
                    existing_created_at,
                    existing_mappings,
                    existing_source_fields,
                ) = existing

                print(f"🔍 _get_supplier_id returned: supplier_id={existing_id}")
                print(f"✅ Found supplier: {existing_name} (ID: {existing_id})")
                print(f"📌 BEFORE update - source_fields: {existing_source_fields}")
                print(
                    f"📌 BEFORE update - mappings count: {len(existing_mappings) if existing_mappings else 0}"
                )
                print(f"📌 BEFORE update - updated_at: {existing_updated_at}")

                # ✅ Get the supplier object for update
                sup = session.query(Supplier).filter(Supplier.id == existing_id).first()

                if sup is None:
                    print(f"❌ Supplier with ID {existing_id} not found in session!")
                    raise ValueError(f"Supplier with ID {existing_id} not found")

                # ✅ Update fields
                print(f"📌 Setting source_fields to: {source_fields}")
                sup.source_fields = source_fields

                print(f"📌 Setting mappings to: {mappings}")
                sup.mappings = mappings

                sup.updated_at = datetime.utcnow()

                supplier_id = sup.id  # Ensure supplier_id is set for return

                print(f"📌 AFTER update - source_fields: {sup.source_fields}")
                print(
                    f"📌 AFTER update - mappings count: {len(sup.mappings) if sup.mappings else 0}"
                )
                print(f"📌 AFTER update - updated_at: {sup.updated_at}")

                logger.info(
                    f"Updated mapping: name={supplier_name}, "
                    f"source_fields={len(source_fields)}, "
                    f"mappings={len(mappings)}"
                )

            # ✅ Commit
            print("🔍 Committing to database...")
            try:
                session.commit()
                print("✅ Commit successful!")

                # ✅ Refresh to verify
                session.refresh(sup)
                print(f"🔍 AFTER REFRESH - source_fields: {sup.source_fields}")
                print(
                    f"🔍 AFTER REFRESH - mappings count: {len(sup.mappings) if sup.mappings else 0}"
                )
                print(f"🔍 AFTER REFRESH - updated_at: {sup.updated_at}")

            except Exception as e:
                print(f"❌ Commit failed: {e}")
                session.rollback()
                raise e

            # ✅ Clear caches
            print("🔍 Clearing caches...")
            self._cache.clear()
            self._supplier_cache.clear()
            print("✅ Caches cleared")

            print("=" * 70)
            print("🔍 SAVE_MAPPINGS DEBUG END")
            print(f"📌 Returning: name={sup.name}")
            print("=" * 70 + "\n")

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
                "mappings": supplier.mappings or [],
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
        print(f"🔍 _get_supplier_id called with: {supplier_name}")

        with local_session() as session:
            sup = session.query(Supplier).filter(Supplier.name == supplier_name).first()

            if sup:
                print(f"✅ Found supplier: {sup.name} (ID: {sup.id})")
                return (
                    sup.id,
                    sup.name,
                    sup.updated_at,
                    sup.created_at,
                    sup.mappings,
                    sup.source_fields,
                )
            else:
                print(f"❌ Supplier '{supplier_name}' not found in database")
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
