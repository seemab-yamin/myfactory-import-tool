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


@router.get("/suppliers", response_class=HTMLResponse)
async def suppliers_list_page(request: Request):
    """Render suppliers list page."""
    if not templates:
        return HTMLResponse("Templates not found.")
    return templates.TemplateResponse(
        request, "suppliers.html", {"request": request, "supplier": None}
    )


@router.get("/suppliers/{supplier_name}", response_class=HTMLResponse)
async def suppliers_page(request: Request, supplier_name: Optional[str] = None):
    """Render suppliers page with list and detail views."""
    if not templates:
        return HTMLResponse("Templates not found.")
    return templates.TemplateResponse(
        request, "suppliers.html", {"request": request, "supplier": supplier_name}
    )


@router.get("/schema", response_class=HTMLResponse)
async def schema_page(request: Request):
    """Render the schema viewer HTML page."""
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")
    return templates.TemplateResponse(request, "schema.html", {"request": request})


@router.get("/add-supplier", response_class=HTMLResponse)
async def add_supplier_page(request: Request):
    """Render the add supplier mapping page."""
    if not templates:
        return HTMLResponse("Templates not found.")
    return templates.TemplateResponse(
        request, "add_supplier.html", {"request": request}
    )


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


@router.get("/api/suppliers")
async def api_get_suppliers():
    """Return list of all supplier names with mappings."""
    if not ensure_configured():
        raise HTTPException(status_code=400, detail="Database not configured.")
    mapper = get_mapper()
    suppliers = mapper.get_all_suppliers()
    return {"suppliers": suppliers, "total": len(suppliers)}


@router.get("/api/mappings/all")
async def api_get_all_mappings():
    """Return all mappings grouped by supplier."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    suppliers = mapper.get_all_suppliers()

    result = {}
    for supplier in suppliers:
        mappings = mapper.get_mappings(supplier, active_only=False)
        result[supplier] = mappings

    return {
        "total_suppliers": len(result),
        "mappings": result,
    }


@router.get("/api/mappings/{supplier}")
async def api_get_mappings(supplier: str, active_only: bool = True):
    """Return full mapping for a specific supplier."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    mappings = mapper.get_mappings(supplier, active_only)
    summary = mapper.get_mapping_summary(supplier)

    return {
        "supplier": supplier,
        "summary": summary,
        "mappings": mappings,
    }


@router.post("/api/mappings/{supplier}")
async def api_save_mapping(
    supplier: str,
    source_field: str = Form(...),
    target_field: str = Form(...),
    active: bool = Form(True),
):
    """Save a mapping for a supplier."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    mapper.save_mapping(supplier, source_field, target_field, active)

    return {
        "status": "created",
        "supplier": supplier,
        "source_field": source_field,
        "target_field": target_field,
        "active": active,
    }


@router.delete("/api/mappings/{supplier}/{source_field}")
async def api_delete_mapping(supplier: str, source_field: str):
    """Delete a mapping for a supplier."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    deleted = mapper.delete_mapping(supplier, source_field)

    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return {"status": "deleted", "supplier": supplier, "source_field": source_field}


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
async def parse_sample_file(file: UploadFile = File(...)):
    """Parse uploaded file and return column names + preview."""
    from io import BytesIO

    import pandas as pd

    try:
        content = await file.read()
        filename = file.filename.lower()

        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(content), nrows=5)
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(BytesIO(content), nrows=5)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type.")

        if df.empty:
            raise HTTPException(status_code=400, detail="File is empty")

        columns = list(df.columns)
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
