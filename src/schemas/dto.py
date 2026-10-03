from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ImportStatus(str, Enum):
    """Import status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DRY_RUN = "dry_run"


@dataclass
class ImportConfigDTO:
    """Import configuration DTO."""

    file_path: str
    mapping: Optional[Dict[str, str]] = None
    delimiter: str = ","
    batch_size: int = 100
    dry_run: bool = False
    table_name: str = "tdProducts"
    supplier_id: Optional[int] = None
    import_id: Optional[str] = None
    skip_header: bool = True
    supplier_name: Optional[str] = "default"

    header_row_index: int = 1
    sheet_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "import_id": self.import_id,
            "mapping": self.mapping,
            "delimiter": self.delimiter,
            "batch_size": self.batch_size,
            "dry_run": self.dry_run,
            "table_name": self.table_name,
            "supplier_name": self.supplier_name,
            "supplier_id": self.supplier_id,
            "header_row_index": self.header_row_index,
            "sheet_name": self.sheet_name,
        }


@dataclass
class ImportResultDTO:
    """Import result summary DTO."""

    status: ImportStatus
    total_rows: int
    imported_rows: int
    failed_rows: int
    skipped_rows: int
    errors: List[str]
    log_file: str
    audit_id: Optional[int] = None
    details: Optional[Dict[str, Any]] = None

    @classmethod
    def from_audit(cls, audit) -> "ImportResultDTO":
        """Create DTO from audit record."""
        return cls(
            status=(
                ImportStatus(audit.status)
                if audit.status in ImportStatus.__members__
                else ImportStatus.FAILED
            ),
            total_rows=audit.rows_processed,
            imported_rows=audit.rows_succeeded,
            failed_rows=audit.rows_failed,
            skipped_rows=audit.rows_skipped,
            errors=[audit.error_message] if audit.error_message else [],
            log_file=str(audit.file_path),
            audit_id=audit.id,
            details=audit.details,
        )
