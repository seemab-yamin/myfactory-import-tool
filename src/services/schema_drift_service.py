"""Schema drift detection and supplier sync service.

Encapsulates the full drift-check pipeline in a transaction-aware,
reusable object so callers (API, scheduler, CLI) don't need to know
the internal steps.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.db import DatabaseManager
from src.logger import get_logger
from src.models import SchemaChangeLog, TargetField

logger = get_logger(__name__)


class SchemaDriftService:
    """Coordinates schema drift detection end-to-end."""

    def __init__(
        self,
        db: DatabaseManager,
        db_session: Session,
        products_table: str,
        attribute_values_table: str,
        apply_sync: bool = True,
    ) -> None:
        if db_session is None:
            raise ValueError("SchemaDriftService requires a non-None db_session")

        self.db = db
        self.db_session = db_session
        self.apply_sync = apply_sync
        self.products_table = products_table
        self.attribute_values_table = attribute_values_table

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------
    def check_and_sync(self) -> dict[str, Any]:
        from src.mapper import sync_all_suppliers
        from src.schema_scanner import compare_schemas

        now = datetime.now(timezone.utc)

        # ---- 1. Live schema ----
        live = self.db.get_live_columns_from_mssql(
            [self.products_table, self.attribute_values_table]
        )
        if not live:
            logger.warning("Drift check: live schema empty — MSSQL unreachable?")
            return self._empty_result(now, reason="live_schema_empty")

        # ---- 2. Cached schema ----
        cached = (
            self.db_session.query(TargetField)
            .filter(
                TargetField.table_name.in_(
                    [self.products_table, self.attribute_values_table]
                )
            )
            .all()
        )
        if not cached:
            logger.warning("Drift check: cache empty — run a refresh first")
            return self._empty_result(now, reason="cache_empty")

        # ---- 3. Diff ----
        diff = compare_schemas(cached, live)
        if not diff["has_changes"]:
            logger.info("Drift check: no changes detected")
            return self._empty_result(now, reason="no_changes")

        # ✅ SNAPSHOT diff into plain dicts BEFORE touching cache or ORM
        added_snapshot = [
            {"field_name": f.field_name, "data_type": f.data_type}
            for f in diff["added"]
        ]
        removed_snapshot = [
            {"field_name": f.field_name, "data_type": f.data_type}
            for f in diff["removed"]
        ]
        changed_snapshot = diff["changed"]

        # ---- 4. Refresh cache first ----
        if self.apply_sync:
            diff["added"] = self._refresh_target_field_cache(live)
        else:
            logger.info("Drift check: apply_sync=False — cache not refreshed")
        # ---- 5. Sync suppliers ----
        suppliers_synced = 0
        if self.apply_sync and (removed_snapshot or added_snapshot or changed_snapshot):
            suppliers_synced = sync_all_suppliers(
                diff,
                self.db_session,
            )

        # ---- 6. Write log using SNAPSHOT (not diff objects) ----
        log = SchemaChangeLog(
            checked_at=now,
            added_fields=added_snapshot,
            removed_fields=removed_snapshot,
            suppliers_synced=suppliers_synced,
            details=(
                f"added={len(added_snapshot)} "
                f"removed={len(removed_snapshot)} "
                f"changed={len(changed_snapshot)} "
                f"synced={suppliers_synced}"
            ),
        )
        self.db_session.add(log)
        self.db_session.flush()
        log_id = log.id

        try:
            self.db_session.commit()
        except Exception:
            self.db_session.rollback()
            raise

        logger.info(
            f"Drift detected — added={len(added_snapshot)} "
            f"removed={len(removed_snapshot)} changed={len(changed_snapshot)} "
            f"synced={suppliers_synced} log_id={log_id}"
        )

        return {
            "checked_at": now.isoformat(),
            "products_table": self.products_table,
            "attribute_values_table": self.attribute_values_table,
            "has_changes": True,
            "added_count": len(added_snapshot),
            "removed_count": len(removed_snapshot),
            "changed_count": len(changed_snapshot),
            "suppliers_synced": suppliers_synced,
            "log_id": log_id,
            "added": [d["field_name"] for d in added_snapshot],
            "removed": [d["field_name"] for d in removed_snapshot],
            "changed": changed_snapshot,
            "reason": None,
        }

    # ------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------
    def _refresh_target_field_cache(
        self,
        live: list[TargetField],
    ) -> list[TargetField]:
        tables = [
            self.products_table,
            self.attribute_values_table,
        ]

        # Remove existing cached schema.
        self.db_session.query(TargetField).filter(
            TargetField.table_name.in_(tables)
        ).delete(synchronize_session="fetch")

        self.db_session.flush()

        # Insert current live schema.
        persisted_fields = []

        for field in live:
            cached_field = TargetField(
                table_name=field.table_name,
                field_name=field.field_name,
                data_type=field.data_type,
                max_length=field.max_length,
                is_nullable=field.is_nullable,
                is_identity=field.is_identity,
                default_value=field.default_value,
            )

            self.db_session.add(cached_field)
            persisted_fields.append(cached_field)

        # Flush so database-generated IDs are populated.
        self.db_session.flush()

        return persisted_fields

    def _empty_result(self, now: datetime, reason: str) -> dict[str, Any]:
        """Uniform empty result shape for short-circuit paths."""
        return {
            "checked_at": now.isoformat(),
            "products_table": self.products_table,
            "attribute_values_table": self.attribute_values_table,
            "has_changes": False,
            "added_count": 0,
            "removed_count": 0,
            "changed_count": 0,
            "suppliers_synced": 0,
            "log_id": None,
            "added": [],
            "removed": [],
            "changed": [],
            "reason": reason,
        }
