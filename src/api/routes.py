"""API routes for MyFactory Import Tool."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from src.config_manager import ensure_configured, get_config_manager
from src.db import local_session, get_db_manager
from src.importer import get_importer, run_import
from src.logger import get_logger
from src.mapper import get_mapper
from src.schema_scanner import get_scanner
from src.services.schema_drift_service import SchemaDriftService

logger = get_logger(__name__)

router = APIRouter()

# Templates
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"
templates = (
    Jinja2Templates(directory=str(TEMPLATE_DIR)) if TEMPLATE_DIR.exists() else None
)
# Constants

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_BATCH_SIZE = 100000
MIN_BATCH_SIZE = 1
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

# ========== HTML Pages ==========


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page."""
    if templates:
        suppliers = get_mapper().get_all_suppliers() if ensure_configured() else []
        return templates.TemplateResponse(
            request, "index.html", {"request": request, "suppliers": suppliers}
        )
    return HTMLResponse("<h1>MyFactory Import Tool</h1><p>API is running.</p>")


@router.get("/mappings-list", response_class=HTMLResponse)
async def mappings_list_page(request: Request):
    """Render mappings list page.

    Side effect: runs a schema drift check on page load. If MSSQL
    is unreachable, the check silently degrades — page still renders.
    """

    if not templates:
        return HTMLResponse("Templates not found.")

    # ---- 1. Suppliers list (always needed) ----
    suppliers = []
    if ensure_configured():
        try:
            suppliers = get_mapper().get_all_suppliers()
        except Exception as e:
            logger.warning(f"Failed to fetch suppliers: {e}")

    # ---- 2. Drift check (best-effort, never blocks the page) ----
    schema_changed = False
    schema_details: dict = {}

    if ensure_configured():
        try:
            with local_session() as session:
                service = SchemaDriftService(session)
                schema_details = service.check_and_sync()
                schema_changed = bool(schema_details.get("has_changes"))
                print(f"TODO: Schema drift check result: {schema_details}")
        except Exception as e:
            logger.warning(f"Schema drift check failed on /mappings-list: {e}")
            schema_details = {"error": str(e), "has_changes": False}

    # ✅ Ensure schema_details always has the expected keys
    schema_details.setdefault("has_changes", False)
    schema_details.setdefault("added_count", 0)
    schema_details.setdefault("removed_count", 0)
    schema_details.setdefault("changed_count", 0)
    schema_details.setdefault("suppliers_synced", 0)
    schema_details.setdefault("added", [])
    schema_details.setdefault("removed", [])
    schema_details.setdefault("changed", [])

    # ---- 3. Render ----
    return templates.TemplateResponse(
        request,
        "mappings_list.html",
        {
            "request": request,
            "suppliers": suppliers,
            "schema_changed": schema_changed,
            "schema_details": schema_details,
            "mapping": None,  # keep for backward compat with template
        },
    )


@router.get("/show-mapping/{supplier_id:int}", response_class=HTMLResponse)
async def mappings_page(request: Request, supplier_id: int):
    """Render mappings detail page for a specific supplier."""
    if not templates:
        return HTMLResponse("Templates not found.")

    mapper = get_mapper()

    # ✅ Get supplier details with source_fields
    supplier = mapper.get_supplier_by_id(supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=404, detail=f"Supplier with ID {supplier_id} not found"
        )
    return templates.TemplateResponse(
        request,
        "show_mapping.html",
        {
            "supplier_id": supplier.get("id"),
            "supplier_name": supplier.get("name"),
            "source_fields": (
                supplier.get("source_fields") if supplier.get("source_fields") else []
            ),
            "supplier_mappings": (
                supplier.get("mappings") if supplier.get("mappings") else {}
            ),
        },
    )


@router.get("/add-mapping", response_class=HTMLResponse)
async def add_mapping_page(request: Request):
    """Render the add mapping mapping page."""
    if not templates:
        return HTMLResponse("Templates not found.")
    return templates.TemplateResponse(request, "add_mapping.html", {"request": request})


# ========== API Endpoints ==========


@router.get("/health")
async def health():
    """Health check endpoint."""
    config = get_config_manager()
    return {
        "status": "healthy",
        "configured": config.is_configured(),
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    supplier_id: int = Form(...),
    dry_run: bool = Form(False),
    batch_size: int = Form(1000),
):
    """
    Upload and import a file.

    Requirements fulfilled:
    1. Input Validation Layer
    2. File Handling Layer
    3. Dry-Run Mode (Synchronous)
    """

    # ============================================================
    # 1. INPUT VALIDATION LAYER
    # ============================================================

    # ✅ 1.1 Ensure configured
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    # ✅ 1.2 Validate file type (.csv, .xlsx, .xls)
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ✅ 1.3 Validate file size (optional but recommended)
    file_size = 0
    try:
        content = await file.read()
        file_size = len(content)
        await file.seek(0)  # Reset file pointer for later use
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)} MB",
        )
    if file_size == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    # ✅ 1.5 Validate batch_size (min 1, max 10000)
    if not isinstance(batch_size, int):
        raise HTTPException(status_code=400, detail="batch_size must be an integer.")

    if batch_size < MIN_BATCH_SIZE:
        raise HTTPException(
            status_code=400, detail=f"batch_size must be at least {MIN_BATCH_SIZE}."
        )

    if batch_size > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400, detail=f"batch_size must be at most {MAX_BATCH_SIZE}."
        )

    # ============================================================
    # 2. FILE HANDLING LAYER
    # ============================================================

    # ✅ 2.1 Save uploaded file to UPLOAD_DIR with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename

    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            # Content is already read, write it
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # ✅ 2.2 Return file_path for background task
    # ✅ 2.3 Handle file read errors (already handled above)

    # ============================================================
    # 3. DRY-RUN MODE (Synchronous)
    # ============================================================

    if dry_run:
        try:
            importer = get_importer()
            result = importer.import_file(
                {
                    "file_path": str(file_path),
                    "supplier_id": supplier_id,
                    "dry_run": True,
                    "batch_size": batch_size,
                }
            )

            # ✅ 3.1 Parse file (delimiter, encoding) - handled by importer
            # ✅ 3.2 Validate against mapping - handled by importer
            # ✅ 3.3 Return preview rows + validation errors

            return {
                "status": "dry_run_completed",
                "supplier_id": supplier_id,
                "total_rows": result.total_rows,
                "preview": (
                    result.details.get("preview_rows", []) if result.details else []
                ),
                "columns": result.details.get("columns", []) if result.details else [],
                "mapping": result.details.get("mapping", {}) if result.details else {},
                "errors": result.errors,
                "warnings": result.warnings if hasattr(result, "warnings") else [],
                "log_file": result.log_file,
                "file_path": str(file_path),
                "file_name": file.filename,
                "batch_size": batch_size,
            }
        except Exception as e:
            logger.error(f"Dry-run failed: {e}")
            raise HTTPException(status_code=500, detail=f"Dry-run failed: {str(e)}")

    # ============================================================
    # 4. BACKGROUND IMPORT
    # ============================================================

    import uuid

    import_id = str(uuid.uuid4())
    # ✅ Background task for full import
    background_tasks.add_task(
        run_import,
        import_id=import_id,  # ✅ Add
        file_path=str(file_path),
        supplier_id=supplier_id,
        batch_size=batch_size,
    )

    return {
        "status": "accepted",
        "message": "Import started in background",
        "import_id": import_id,  # ✅ Return to client
        "supplier_id": supplier_id,
        "file_path": str(file_path),
        "file_name": file.filename,
        "batch_size": batch_size,
    }


@router.get("/history")
async def get_history(supplier: Optional[str] = None, limit: int = 50):
    """Get import history."""
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    importer = get_importer()
    history = importer.get_import_history(supplier, limit)
    return {"total": len(history), "supplier": supplier or "all", "history": history}


@router.get("/history/{audit_id}")
async def get_audit_detail(audit_id: int):
    """Get detailed audit record."""
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    with local_session() as session:
        from src.models import ImportAudit

        audit = session.query(ImportAudit).filter(ImportAudit.id == audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit record not found")
        return audit.to_dict()


@router.get("/api/mappings-list")
async def api_get_mappings_list():
    """Return list of all suppliers."""

    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")
    mapper = get_mapper()
    suppliers = mapper.get_all_suppliers()
    return {"suppliers": suppliers, "total": len(suppliers)}


@router.get("/api/mapping_name/exists/{supplier_name}")
async def mapping_name_exists(supplier_name: str):
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    mapper = get_mapper()
    exists = mapper.mapping_name_exists(supplier_name)

    return {"supplier_name": supplier_name, "exists": exists}


@router.get("/api/mappings/{supplier_id:int}")
async def api_get_mappings(supplier_id: int, active_only: bool = False):
    """Return full mapping for a specific supplier by ID."""

    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    mappings = mapper.get_mappings(supplier_id, active_only)

    # Get supplier name for response
    from src.models import Supplier

    with local_session() as session:
        supplier = session.query(Supplier).filter(Supplier.id == supplier_id).first()
        supplier_name = supplier.name if supplier else None

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "total_mappings": len(mappings),
        "mappings": mappings,  # {source_field: target_field}
    }


@router.post("/api/mappings/{supplier_name:str}")
async def api_save_mappings(
    supplier_name: str,
    source_fields: List[str] = Body(...),
    mappings: List[dict] = Body(...),
    is_new_supplier: bool = Body(False),
):
    """Save a mappings for a supplier."""

    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    _, supplier_id = mapper.save_mappings(
        supplier_name=supplier_name,
        source_fields=source_fields,
        mappings=mappings,
        is_new_supplier=is_new_supplier,
    )

    return {
        "status": "created",
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
    }


@router.delete("/api/suppliers/{supplier_id:int}")
async def api_delete_supplier(supplier_id: int):
    """Delete a supplier and all associated mappings."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    deleted = mapper.delete_supplier(supplier_id)

    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Supplier with ID {supplier_id} not found"
        )

    return {
        "status": "deleted",
        "supplier_id": supplier_id,
        "message": f"Supplier {supplier_id} and all mappings deleted successfully",
    }


@router.post("/setup")
async def run_setup():
    """Run interactive setup via API."""
    config = get_config_manager()
    success = config.interactive_setup()
    if success:
        return {"status": "success", "message": "Setup completed successfully"}
    else:
        raise HTTPException(status_code=400, detail="Setup failed")


@router.get("/files/{file_path:path}")
async def download_file(file_path: str):
    """Download a file."""
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


# ========== Schema Models ==========


class ColumnSchema(BaseModel):
    name: str
    type: str
    nullable: bool
    max_length: Optional[int] = None
    default: Optional[str] = None


class TableSchemaResponse(BaseModel):
    table_name: str
    total_columns: int
    columns: List[ColumnSchema]


@router.get("/api/schema")
async def api_schema(
    refresh_cache: bool = False,
    sort_by: str = "id",
):
    """Return JSON schema for the default table."""

    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    config = get_config_manager()
    default_products_table = config.get().default_products_table
    db = get_db_manager()

    if refresh_cache:
        columns = db.get_table_columns(
            sort_by=sort_by, table_name=default_products_table, use_cache=False
        )
    else:
        columns = db.get_table_columns(
            sort_by=sort_by, table_name=default_products_table, use_cache=True
        )
    return {
        "table_name": default_products_table,
        "total_columns": len(columns),
        "columns": columns,
    }


@router.post("/api/parse-sample")
async def parse_sample_file(
    file: UploadFile = File(...),
):
    from io import BytesIO

    import pandas as pd

    try:
        content = await file.read()

        # Determine file type
        filename = file.filename.lower()
        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(content), nrows=5)
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(BytesIO(content), nrows=5)
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Please upload CSV or Excel.",
            )

        if df.empty:
            raise HTTPException(status_code=400, detail="File is empty")

        # Get columns
        columns = list(df.columns)

        # Get preview (first 5 rows)
        preview = (
            df.head(5)
            .replace({pd.NA: None, float("nan"): None})
            .to_dict(orient="records")
        )

        return {
            "columns": columns,
            "preview": preview,
            "row_count": len(df),
            "column_count": len(columns),
        }

    except Exception as e:
        logger.error(f"Parse error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")


# ============================================================
# Schema Drift Detection
# ============================================================


@router.post("/api/schema/check")
async def api_check_schema_drift(apply_sync: bool = True):
    """Manually trigger schema drift detection. Has side effects — POST only."""
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    try:
        with local_session() as session:
            service = SchemaDriftService(session, apply_sync=apply_sync)
            return service.check_and_sync()
    except Exception as e:
        logger.error(f"Schema drift detection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Schema drift detection failed: {str(e)}",
        )


@router.get("/api/schema/change-log")
async def api_schema_change_log(limit: int = 20):
    """
    Return recent SchemaChangeLog entries (newest first).

    Query params:
        limit (int): Max rows to return (default 20).
    """
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    from src.models import SchemaChangeLog

    with local_session() as session:
        logs = (
            session.query(SchemaChangeLog)
            .order_by(SchemaChangeLog.checked_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "total": len(logs),
            "logs": [log.to_dict() for log in logs],
        }
