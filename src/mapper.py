"""Dynamic field mapping for Myfactory import with CRUD operations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy.orm.attributes import flag_modified

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

        Reads from Supplier.mappings JSON (dict keyed by target_field_name).

        Returns:
            List of dicts with keys:
                - source_field: str | None
                - target_field: str (target field name — the dict key)
                - is_mandatory: bool
                - is_db_required: bool
                - is_active: bool
                - prepopulated_value: str | None
        """

        cache_key = f"{supplier_id}_{active_only}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        with local_session() as session:
            supplier = (
                session.query(Supplier).filter(Supplier.id == supplier_id).first()
            )

            mappings = []
            if supplier and supplier.mappings:
                raw = supplier.mappings  # dict: {target_name: {...}}

                for target_name, m in raw.items():
                    # active_only: skip inactive
                    if active_only and not m.get("is_active", True):
                        continue

                    mappings.append(
                        {
                            "source_field": m.get("source_field"),
                            "target_field": target_name,  # key is the target name
                            "is_mandatory": m.get("is_mandatory", False),
                            "is_db_required": m.get("is_db_required", False),
                            "is_active": m.get("is_active", True),
                            "prepopulated_value": m.get("prepopulated_value"),
                        }
                    )

            self._cache[cache_key] = mappings
            return mappings

    def get_mapping_dict(
        self, supplier_id: int, active_only: bool = True
    ) -> Dict[str, str]:
        raw = self.get_mappings(supplier_id, active_only)
        return {
            m["source_field"]: m["target_field"]
            for m in raw
            if m.get("source_field") and m.get("target_field")
        }

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
        header_row_index: Optional[int] = None,
        sheet_name: Optional[str] = None,
        delimiter: str = ",",
        is_new_supplier: bool = False,
    ):

        # ✅ Normalize List[dict] → dict keyed by target_field_name
        mappings_dict = (
            {m["target_field_name"]: m for m in mappings if m.get("target_field_name")}
            if mappings
            else {}
        )
        with local_session() as session:
            # ✅ Use different variable names to avoid confusion
            # fetch supplier by name
            if is_new_supplier:
                sup = None
            else:
                sup = self._get_supplier(supplier_name, session)

            if not sup:
                # case 1: if supplier does not exist, create a new one
                sup = Supplier(
                    name=supplier_name,
                    source_fields=source_fields,
                    mappings=mappings_dict,
                    header_row_index=header_row_index,
                    sheet_name=sheet_name,
                    delimiter=delimiter,
                )
                session.add(sup)
                session.flush()
                logger.info(
                    f"Created mapping: name={supplier_name}, "
                    f"source_fields={len(source_fields)}, "
                    f"mappings={len(mappings_dict)}"
                )
            else:
                # case 2: if supplier exists, update the existing one
                # case 2a: if source_fields is provided, update it; otherwise, keep existing
                if source_fields:
                    sup.source_fields = source_fields
                    # if no mappings given, means the source fields are updated so we need to flag the schema_changed_flag to True
                    if not mappings_dict:
                        schema_changed_flag = False
                        # we iterate over the existing mappings to flag if any of the source fields are no longer present in the new source_fields list
                        new_updated_mappings = {}
                        for target_field, mapping in sup.mappings.items():
                            if (
                                mapping.get("source_field")
                                and mapping.get("source_field") not in source_fields
                            ):
                                schema_changed_flag = True
                                mapping["previous_source_field"] = mapping[
                                    "source_field"
                                ]
                                mapping["source_field"] = None
                                mapping["mapping_status"] = "removed"
                            else:
                                mapping["mapping_status"] = "mapped"
                            new_updated_mappings[target_field] = mapping
                        sup.mappings = new_updated_mappings
                        flag_modified(sup, "mappings")
                        sup.schema_changed_flag = schema_changed_flag

                # case 2b: update mappings, header_row_index, sheet_name, delimiter
                if mappings_dict:
                    sup.mappings = mappings_dict
                    sup.schema_changed_flag = False
                if header_row_index:
                    sup.header_row_index = header_row_index
                if sheet_name:
                    sup.sheet_name = sheet_name
                if delimiter:
                    sup.delimiter = delimiter
            logger.info(
                f"Updated/Added mapping: name={supplier_name}, "
                f"source_fields={len(source_fields)}, "
                f"mappings={len(sup.mappings)}, "
                f"supplier_id={sup.id}"
            )

            # ✅ Commit
            try:
                session.commit()
            except Exception as e:
                session.rollback()
                raise e
            # ✅ Clear caches
            self._cache.clear()
            self._supplier_cache.clear()
            return sup.id

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
            suppliers = session.query(Supplier).order_by(Supplier.name).all()
            suppliers = [
                (
                    s.id,
                    s.name,
                    s.source_fields,
                    s.mappings,
                    s.created_at,
                    s.updated_at,
                    s.schema_changed_at,
                    s.schema_changed_flag,
                    s.header_row_index,
                    s.sheet_name,
                    s.delimiter,
                )
                for s in suppliers
            ]  # Convert to list of tuples
            return suppliers

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
            if supplier is None:
                raise ValueError(f"Supplier with ID {supplier_id} not found")

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
                "schema_changed_flag": supplier.schema_changed_flag,
                "schema_changed_at": (
                    supplier.schema_changed_at.isoformat()
                    if supplier.schema_changed_at
                    else None
                ),
                "header_row_index": supplier.header_row_index,
                "sheet_name": supplier.sheet_name,
                "delimiter": supplier.delimiter,
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

    def sync_supplier_excel(
        self,
        supplier_id: int,
        new_source_columns: list[str],
    ) -> dict:
        """
        Compare new file columns against saved supplier mappings.

        Does not modify or save anything.
        """

        supplier = self.get_supplier_by_id(supplier_id)

        if supplier is None:
            raise ValueError(f"Supplier with ID {supplier_id} not found")

        mappings = supplier.get("mappings") or {}

        # Deduplicate while preserving file column order.
        new_columns = list(
            dict.fromkeys(
                column
                for column in new_source_columns
                if isinstance(column, str) and column.strip()
            )
        )

        new_column_set = set(new_columns)

        kept = []
        broken = []

        # Track every source column currently assigned to a target.
        existing_source_columns = set()

        for target_field, mapping in mappings.items():
            source_column = mapping.get("source_field")

            if not source_column:
                continue

            existing_source_columns.add(source_column)

            if source_column in new_column_set:
                kept.append(
                    {
                        "target_field": target_field,
                        "source_column": source_column,
                    }
                )
                continue

            match = self.auto_match_fields(
                new_columns,
                [source_column],
            )

            suggested_source = None

            if match:
                suggestion = match.get(source_column)
                if suggestion:
                    suggested_source = suggestion.get("source_column")

            broken.append(
                {
                    "target_field": target_field,
                    "old_source": source_column,
                    "suggested_source": suggested_source,
                    "is_mandatory": mapping.get("is_mandatory", False),
                    "is_db_required": mapping.get("is_db_required", False),
                }
            )

        new = [
            column for column in new_columns if column not in existing_source_columns
        ]

        return {
            "kept": kept,
            "broken": broken,
            "new": new,
            "source_columns": new_columns,
        }

    def apply_sync(
        self,
        supplier_id: int,
        resolved_mappings: list[dict],
    ) -> bool:
        """Apply resolved Excel source mappings using the existing save flow."""

        # Validate that every mapping has been resolved.
        broken = [
            mapping for mapping in resolved_mappings if not mapping.get("source_column")
        ]

        if broken:
            raise ValueError(
                f"{len(broken)} mappings unresolved: "
                f"{[m['target_field'] for m in broken]}"
            )

        supplier = self.get_supplier_by_id(supplier_id)

        if supplier is None:
            raise ValueError(f"Supplier with ID {supplier_id} not found")

        mappings = [
            {
                **mapping,
                "source_field": mapping["source_column"],
                "target_field_name": mapping["target_field"],
            }
            for mapping in resolved_mappings
        ]

        self.save_mappings(
            supplier_name=supplier["name"],
            source_fields=supplier.get("source_fields") or [],
            mappings=mappings,
            header_row_index=supplier.get("header_row_index"),
            sheet_name=supplier.get("sheet_name"),
            delimiter=supplier.get("delimiter", ","),
        )

        return True

    # ============================================================
    # AUTO-MATCH FIELDS
    # ============================================================

    def auto_match_fields(
        self,
        source_columns: List[str],
        target_fields: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Deterministic + fuzzy field auto-matching.

        Returns:
            {
                target_field_name: {
                    "source_column": str,
                    "match_type": "exact" | "case_insensitive" | "normalized" | "fuzzy",
                    "score": float,   # 1.0 for deterministic; 0.70–1.0 for fuzzy
                }
            }

        Priority (per target, first match wins):
            1. Exact match (case-sensitive)         → match_type="exact",           score=1.0
            2. Case-insensitive match               → match_type="case_insensitive", score=1.0
            3. Normalized match (lower, strip,
            spaces → underscores)                → match_type="normalized",       score=1.0
            4. Fuzzy (rapidfuzz.ratio) with
            dynamic threshold + best-gap rule    → match_type="fuzzy",            score=0.70–1.0

        Rules:
            - A source column can be matched to only ONE target.
            - Deterministic passes (1–3) always run before fuzzy.
            - Fuzzy pass only considers targets still unmatched after Pass 3.
            - Fuzzy pass requires:
                best_score >= dynamic_threshold(target)
                AND (best_score - second_best_score) > 0.05
            - Unmatched targets are omitted.
            - Duplicate source column names are deduplicated (first wins).

        Logs:
            Per-category match counts (exact / case_insensitive / normalized / fuzzy)
            and total unmatched targets + unused sources.
        """
        if not source_columns or not target_fields:
            return {}

        # ---------- Deduplicate sources (preserve order, first wins) ----------
        seen = set()
        unique_sources: List[str] = []
        for src in source_columns:
            if not isinstance(src, str) or not src.strip():
                continue
            if src in seen:
                logger.warning(f"Duplicate source column ignored: '{src}'")
                continue
            seen.add(src)
            unique_sources.append(src)

        if not unique_sources:
            return {}

        suggestions: Dict[str, Dict[str, Any]] = {}
        available_sources = list(unique_sources)

        # ---------- Pass 1: Exact match (case-sensitive) ----------
        for target in target_fields:
            if target in available_sources:
                suggestions[target] = {
                    "source_column": target,
                    "match_type": "exact",
                    "score": 1.0,
                }
                available_sources.remove(target)

        # ---------- Pass 2: Case-insensitive ----------
        if available_sources:
            lower_map: Dict[str, str] = {}
            for src in available_sources:
                lower_map.setdefault(src.lower(), src)  # first wins

            for target in target_fields:
                if target in suggestions:
                    continue
                key = target.lower()
                if key in lower_map:
                    src = lower_map.pop(key)
                    suggestions[target] = {
                        "source_column": src,
                        "match_type": "case_insensitive",
                        "score": 1.0,
                    }
                    available_sources.remove(src)

        # ---------- Pass 3: Normalized ----------
        if available_sources:

            def normalize(s: str) -> str:
                return s.strip().replace(" ", "_").lower()

            norm_map: Dict[str, str] = {}
            for src in available_sources:
                norm_map.setdefault(normalize(src), src)

            for target in target_fields:
                if target in suggestions:
                    continue
                key = normalize(target)
                if key in norm_map:
                    src = norm_map.pop(key)
                    suggestions[target] = {
                        "source_column": src,
                        "match_type": "normalized",
                        "score": 1.0,
                    }
                    available_sources.remove(src)

        # ---------- Pass 4: Fuzzy (rapidfuzz) ----------
        for target in target_fields:
            if target in suggestions:
                continue
            if not available_sources:
                break

            threshold = _dynamic_threshold(target)
            t_norm = _normalize_for_fuzzy(target)

            scores: List[Tuple[float, str]] = []
            for src in available_sources:
                score = fuzz.ratio(t_norm, _normalize_for_fuzzy(src)) / 100.0
                scores.append((score, src))

            scores.sort(reverse=True)
            best_score, best_src = scores[0]
            second_score = scores[1][0] if len(scores) > 1 else 0.0

            if best_score >= threshold and (best_score - second_score) > 0.05:
                suggestions[target] = {
                    "source_column": best_src,
                    "match_type": "fuzzy",
                    "score": round(best_score, 3),
                }
                available_sources.remove(best_src)

        # ---------- Summary logging ----------
        exact_count = sum(1 for v in suggestions.values() if v["match_type"] == "exact")
        ci_count = sum(
            1 for v in suggestions.values() if v["match_type"] == "case_insensitive"
        )
        norm_count = sum(
            1 for v in suggestions.values() if v["match_type"] == "normalized"
        )
        fuzzy_count = sum(1 for v in suggestions.values() if v["match_type"] == "fuzzy")
        unmatched_count = len(target_fields) - len(suggestions)

        logger.info(
            "Auto-match summary | "
            f"exact={exact_count} "
            f"case_insensitive={ci_count} "
            f"normalized={norm_count} "
            f"fuzzy={fuzzy_count} "
            f"unmatched={unmatched_count} "
            f"unused_sources={len(available_sources)}"
        )

        return suggestions

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

    def _get_supplier(self, supplier_name: str, session):
        """Get supplier by name."""

        sup = session.query(Supplier).filter(Supplier.name == supplier_name).first()
        return sup if sup else None


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
    removed = schema_diff.get("removed", [])
    added = schema_diff.get("added", [])
    changed = schema_diff.get("changed", [])

    mappings = dict(supplier.mappings or {})
    mutated = False

    # 1. Removed fields
    for field in removed:
        name = field.field_name

        if name in mappings:
            del mappings[name]
            mutated = True

    # 2. Added fields
    for field in added:
        name = field.field_name

        mappings[name] = {
            "data_type": field.data_type,
            "max_length": field.max_length,
            "is_nullable": field.is_nullable,
            "is_identity": field.is_identity,
        }
        mutated = True

    # 3. Changed fields
    for change in changed:
        name = change["field_name"]
        new_field = change["new"]

        old_mapping = mappings.get(name)
        if old_mapping is None:
            continue

        preserved_mapping = {
            key: value
            for key, value in old_mapping.items()
            if key
            not in {
                "target_field_name",
                "target_field_id",
                "data_type",
                "max_length",
                "is_nullable",
                "is_identity",
            }
        }

        mappings[name] = {
            **preserved_mapping,
            "target_field_name": new_field.field_name,
            "target_field_id": new_field.id,
            "data_type": new_field.data_type,
            "max_length": new_field.max_length,
            "is_nullable": new_field.is_nullable,
            "is_identity": new_field.is_identity,
        }

        mutated = True

    if not mutated:
        return False

    supplier.mappings = mappings

    if not supplier.schema_changed_flag:
        supplier.schema_changed_at = datetime.now(timezone.utc)
        supplier.schema_changed_flag = True

    return True


def sync_all_suppliers(schema_diff: dict, db_session) -> int:
    """
    Apply a schema diff to all suppliers in a single transaction.

    - Calls sync_supplier_json() per supplier.
    - Commits once at the end → atomic batch.
    - Rolls back on any error.

    Args:
        schema_diff: Output from compare_schemas()
        db_session:  SQLAlchemy Session (caller-provided)

    Returns:
        Count of suppliers whose mappings were actually mutated.
    """

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


# ============================================================
# FUZZY MATCHING HELPERS (used by FieldMapper.auto_match_fields)
# ============================================================


def _normalize_for_fuzzy(s: str) -> str:
    """Aggressive normalization: strip, lower, remove spaces and underscores."""
    return s.strip().lower().replace(" ", "").replace("_", "")


def _dynamic_threshold(target: str) -> float:
    """
    Length-aware similarity threshold.

    Shorter target names require higher confidence (fewer chars → more ambiguity).
    """
    length = len(target)
    if length <= 4:
        return 0.90
    if length <= 8:
        return 0.80
    return 0.70
