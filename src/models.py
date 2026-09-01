"""SQLAlchemy models for MyFactory Import Tool."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class ImportStatus(str, Enum):
    """Import status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class TargetField(Base):
    """Cached product table column information."""

    __tablename__ = "target_fields"
    __table_args__ = (
        UniqueConstraint("table_name", "field_name", name="uq_table_column"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="tdProducts"
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    data_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    max_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_identity: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # relation
    mapping_config = relationship("MappingConfig", back_populates="target_field")

    def __repr__(self) -> str:
        return f"<TargetField(table={self.table_name}, column={self.field_name}, type={self.data_type})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "table_name": self.table_name,
            "field_name": self.field_name,
            "data_type": self.data_type,
            "max_length": self.max_length,
            "is_nullable": self.is_nullable,
            "is_identity": self.is_identity,
            "default_value": self.default_value,
            "discovered_at": (
                self.discovered_at.isoformat() if self.discovered_at else None
            ),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_inspector(
        cls, table_name: str, field_info: Dict[str, Any]
    ) -> "TargetField":
        """Create a TargetField from SQLAlchemy inspector data."""
        return cls(
            table_name=table_name,
            field_name=field_info["name"],
            data_type=str(field_info["type"]),
            max_length=field_info.get("length"),
            is_nullable=field_info.get("nullable", True),
            is_identity=field_info.get("identity", False),
            default_value=(
                str(field_info.get("default")) if field_info.get("default") else None
            ),
        )


class MappingConfig(Base):
    """Supplier-to-table field mapping configuration."""

    __tablename__ = "mapping_config"
    __table_args__ = (
        UniqueConstraint("supplier_name", "target_field_id", name="uq_supplier_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_field: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    prepopulated_value: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    target_field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_fields.id"), nullable=True
    )
    target_field = relationship("TargetField", back_populates="mapping_config")

    def __repr__(self) -> str:
        return f"<MappingConfig(supplier={self.supplier_name}, source={self.source_field}->{self.target_field})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "supplier_name": self.supplier_name,
            "source_field": self.source_field,
            "target_field": self.target_field,
            "is_active": self.is_active,
            "is_mandatory": self.is_mandatory,
            "prepopulated_value": self.prepopulated_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ImportAudit(Base):
    """Audit log for all import operations."""

    __tablename__ = "import_audit"
    __table_args__ = (
        UniqueConstraint(
            "supplier_name",
            "file_name",
            "started_at",
            name="uq_supplier_file_timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    table_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="tdProducts"
    )

    rows_processed: Mapped[int] = mapped_column(Integer, default=0)
    rows_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Duplicates/validation failures

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ImportStatus.PENDING.value
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Detailed logs (JSON)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<ImportAudit(id={self.id}, supplier={self.supplier_name}, status={self.status})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "supplier_name": self.supplier_name,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "table_name": self.table_name,
            "rows_processed": self.rows_processed,
            "rows_succeeded": self.rows_succeeded,
            "rows_failed": self.rows_failed,
            "rows_skipped": self.rows_skipped,
            "status": self.status,
            "error_message": self.error_message,
            "dry_run": self.dry_run,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "details": self.details,
        }

    @classmethod
    def create_from_import(
        cls,
        supplier_name: str,
        file_path: str,
        table_name: str = "tdProducts",
        dry_run: bool = False,
    ) -> "ImportAudit":
        """Create a new audit record for an import."""
        return cls(
            supplier_name=supplier_name,
            file_name=Path(file_path).name,
            file_path=str(file_path),
            table_name=table_name,
            dry_run=dry_run,
            status=ImportStatus.RUNNING.value,
            started_at=datetime.utcnow(),
        )

    def complete(
        self,
        rows_processed: int,
        rows_succeeded: int,
        rows_failed: int = 0,
        rows_skipped: int = 0,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Mark audit record as completed."""
        self.rows_processed = rows_processed
        self.rows_succeeded = rows_succeeded
        self.rows_failed = rows_failed
        self.rows_skipped = rows_skipped
        self.completed_at = datetime.utcnow()
        self.status = (
            ImportStatus.FAILED.value if error_message else ImportStatus.SUCCESS.value
        )
        self.error_message = error_message
        if details:
            self.details = details


class ImportSettings(Base):
    """Global import settings stored in local DB."""

    __tablename__ = "import_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<ImportSettings(key={self.key}, value={self.value[:20] if self.value else ''}...)>"


# === Data Transfer Objects (DTOs) for import/export ===


@dataclass
class ImportConfigDTO:
    """Import configuration DTO."""

    file_path: str
    mapping: Optional[Dict[str, str]] = None
    delimiter: str = ","
    batch_size: int = 100
    dry_run: bool = False
    table_name: str = "tdProducts"
    supplier_name: str = "default"
    skip_header: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "mapping": self.mapping,
            "delimiter": self.delimiter,
            "batch_size": self.batch_size,
            "dry_run": self.dry_run,
            "table_name": self.table_name,
            "supplier_name": self.supplier_name,
            "skip_header": self.skip_header,
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
    def from_audit(cls, audit: ImportAudit) -> "ImportResultDTO":
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


# === Helper functions ===


def get_table_name(table_name: Optional[str] = None) -> str:
    """Get table name with default fallback."""
    if table_name:
        return table_name
    from src.config_manager import get_config_manager

    config = get_config_manager()
    return config.get().default_products_table


# === Import for convenience ===
from pathlib import Path
