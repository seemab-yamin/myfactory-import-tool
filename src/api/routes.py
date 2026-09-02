"""API routes for MyFactory Import Tool."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from src.config_manager import ensure_configured, get_config_manager
from src.db import local_session
from src.importer import get_importer, run_import
from src.logger import get_logger
from src.mapper import get_mapper
from src.schema_scanner import get_scanner

logger = get_logger(__name__)

router = APIRouter()

# Templates
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"
templates = (
    Jinja2Templates(directory=str(TEMPLATE_DIR)) if TEMPLATE_DIR.exists() else None
)

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


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
    """Render mappings list page."""
    if not templates:
        return HTMLResponse("Templates not found.")
    return templates.TemplateResponse(
        request, "mappings_list.html", {"request": request, "mapping": None}
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

    # ✅ Get existing mappings
    supplier_mappings = mapper.get_inverse_mapping(supplier_id)

    # ✅ Get source fields (column headers from uploaded file)
    source_fields = supplier.get("source_fields", [])

    # ✅ Build mapping state: source_field -> target_field
    mapping_state = {}
    for field in source_fields:
        # Check if this source field already has a mapping
        mapped_target = None
        for target, details in supplier_mappings.items():
            if details.get("source_field") == field:
                mapped_target = target
                break
        mapping_state[field] = mapped_target

    return templates.TemplateResponse(
        request,
        "show_mapping.html",
        {
            "request": request,
            "supplier_id": supplier_id,
            "supplier_name": supplier.get("name"),
            "source_fields": source_fields,  # ✅ Pass source fields
            "mapping_state": mapping_state,  # ✅ Pass mapping state
            "supplier_mappings": supplier_mappings,
            "target_fields": mapper.get_target_fields(),  # ✅ All available target fields
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
    supplier: str = Form(...),
    dry_run: bool = Form(False),
    batch_size: int = Form(1000),
):
    """Upload and import a file."""
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    file_path = (
        UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    )

    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    if dry_run:
        importer = get_importer()
        result = importer.import_file(
            {
                "file_path": str(file_path),
                "supplier_name": supplier,
                "dry_run": True,
                "batch_size": batch_size,
            }
        )
        return {
            "status": "dry_run_completed",
            "supplier": supplier,
            "total_rows": result.total_rows,
            "preview": result.details.get("preview_rows", []) if result.details else [],
            "columns": result.details.get("columns", []) if result.details else [],
            "mapping": result.details.get("mapping", {}) if result.details else {},
            "errors": result.errors,
            "log_file": result.log_file,
            "file_path": str(file_path),
        }

    background_tasks.add_task(run_import)
    return {
        "status": "accepted",
        "message": "Import started in background",
        "supplier": supplier,
        "file_path": str(file_path),
        "file_name": file.filename,
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
    from src.db import local_session
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
async def api_save_mapping(
    supplier_name: str,
    source_field: str = Form(...),
    target_field_id: int = Form(...),
    is_active: bool = Form(True),
    is_mandatory: bool = Form(False),
    prepopulated_value: Optional[str] = Form(None),
):
    """Save a mapping for a supplier."""

    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    supplier_id, _ = mapper.save_mapping(
        supplier_name=supplier_name,
        source_field=source_field,
        target_field_id=target_field_id,
        is_active=is_active,
        is_mandatory=is_mandatory,
        prepopulated_value=prepopulated_value,
    )

    return {
        "status": "created",
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "source_field": source_field,
        "target_field_id": target_field_id,
        "is_active": is_active,
        "is_mandatory": is_mandatory,
        "prepopulated_value": prepopulated_value,
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
    use_cache: bool = True,
    simplified: bool = False,
    refresh_cache: bool = False,
):
    """Return JSON schema for the default table."""

    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")

    config = get_config_manager()
    default_products_table = config.get().default_products_table
    scanner = get_scanner()

    if refresh_cache:
        scanner.refresh_cache(default_products_table)

    if not scanner.table_exists(default_products_table):
        raise HTTPException(
            status_code=404, detail=f"Table '{default_products_table}' not found."
        )

    if simplified:
        columns = scanner.get_columns_for_mapping(default_products_table, use_cache)
    else:
        columns = scanner.get_table_schema(default_products_table, use_cache)

    return {
        "table_name": default_products_table,
        "total_columns": len(columns),
        "columns": columns,
    }


@router.post("/api/parse-sample")
async def parse_sample_file(
    file: UploadFile = File(...),
    supplier_name: str = Form(...),
):
    """
    Parse uploaded file and return column names + preview.
    Also saves the source fields to the supplier record.
    """
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

        # ✅ Save source fields to supplier
        mapper = get_mapper()

        # First, get or create the supplier
        supplier_id = mapper._get_or_create_supplier(supplier_name)

        # Then save the source fields
        saved = mapper.save_source_fields(supplier_id, columns)

        if not saved:
            logger.warning(f"Failed to save source fields for supplier {supplier_name}")

        return {
            "columns": columns,
            "preview": preview,
            "row_count": len(df),
            "column_count": len(columns),
            "supplier_id": supplier_id,
            "source_fields_saved": saved,
        }

    except Exception as e:
        logger.error(f"Parse error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
