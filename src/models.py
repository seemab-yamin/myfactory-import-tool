from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum


class ImportStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DRY_RUN = "dry_run"


@dataclass
class ImportConfig:
    """Import configuration"""

    file_path: str
    mapping: Dict[str, str]
    delimiter: str = ","
    batch_size: int = 100
    dry_run: bool = False


@dataclass
class ImportResult:
    """Import result summary"""

    status: ImportStatus
    total_rows: int
    imported_rows: int
    failed_rows: int
    errors: List[str]
    log_file: str
