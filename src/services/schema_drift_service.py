"""Schema drift detection and supplier sync service.

Encapsulates the full drift-check pipeline in a transaction-aware,
reusable object so callers (API, scheduler, CLI) don't need to know
the internal steps.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from src.logger import get_logger
from src.models import SchemaChangeLog, TargetField

logger = get_logger(__name__)


class SchemaDriftService:
    """Coordinates schema drift detection end-to-end."""

    def __init__(
        self,
        db_session: Session,
        table_name: str = "tdProducts",
        apply_sync: bool = True,
    ) -> None:
        if db_session is None:
            raise ValueError("SchemaDriftService requires a non-None db_session")

        self.db = db_session
        self.table_name = table_name
        self.apply_sync = apply_sync

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------
    def check_and_sync(self) -> Dict[str, Any]:
        from src.mapper import sync_all_suppliers
        from src.schema_scanner import compare_schemas, get_live_schema_as_target_fields

        now = datetime.now(timezone.utc)

        # ---- 1. Live schema ----
        live = get_live_schema_as_target_fields(self.table_name)
        if not live:
            logger.warning("Drift check: live schema empty — MSSQL unreachable?")
            return self._empty_result(now, reason="live_schema_empty")

        # ---- 2. Cached schema ----
        cached = (
            self.db.query(TargetField)
            .filter(TargetField.table_name == self.table_name)
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

        # ---- 4. Sync suppliers ----
        suppliers_synced = 0
        if self.apply_sync and removed_snapshot:
            suppliers_synced = sync_all_suppliers(diff, self.db)

        # ---- 5. Refresh cache (destructive) ----
        self._refresh_target_field_cache(live)

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
        self.db.add(log)
        self.db.flush()
        log_id = log.id

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        logger.info(
            f"Drift detected — added={len(added_snapshot)} "
            f"removed={len(removed_snapshot)} changed={len(changed_snapshot)} "
            f"synced={suppliers_synced} log_id={log_id}"
        )

        return {
            "checked_at": now.isoformat(),
            "table_name": self.table_name,
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
    def _refresh_target_field_cache(self, live: List[TargetField]) -> None:
        self.db.query(TargetField).filter(
            TargetField.table_name == self.table_name
        ).delete(synchronize_session=False)
        self.db.flush()  # ✅ Execute DELETE before INSERTing new rows

        for f in live:
            self.db.add(
                TargetField(
                    table_name=self.table_name,
                    field_name=f.field_name,
                    data_type=f.data_type,
                    max_length=f.max_length,
                    is_nullable=f.is_nullable,
                    is_identity=f.is_identity,
                    default_value=f.default_value,
                )
            )

    def _empty_result(self, now: datetime, reason: str) -> Dict[str, Any]:
        """Uniform empty result shape for short-circuit paths."""
        return {
            "checked_at": now.isoformat(),
            "table_name": self.table_name,
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
