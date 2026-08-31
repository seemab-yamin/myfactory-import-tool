import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src.config_manager import ensure_configured, get_config_manager
from src.db import local_session
from src.importer import get_importer, run_import
from src.logger import get_logger
from src.mapper import get_mapper
from src.schema_scanner import get_scanner

logger = get_logger(__name__)


def find_available_port(start_port: int = 8000) -> int:
    """Find the first available port starting from start_port."""
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1


app = FastAPI(
    title="MyFactory Import Tool",
    description="Import products from CSV/Excel to Myfactory CRM",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
templates = (
    Jinja2Templates(directory=str(TEMPLATE_DIR)) if TEMPLATE_DIR.exists() else None
)

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page."""
    if templates:
        suppliers = get_mapper().get_all_suppliers() if ensure_configured() else []
        return templates.TemplateResponse(
            request, "index.html", {"request": request, "suppliers": suppliers}
        )
    return HTMLResponse("""
        <h1>MyFactory Import Tool</h1>
        <p>API is running. Visit <a href="/docs">/docs</a> for API documentation.</p>
    """)


@app.get("/health")
async def health():
    """Health check endpoint."""
    config = get_config_manager()
    return {
        "status": "healthy",
        "configured": config.is_configured(),
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    supplier: str = Form(...),
    dry_run: bool = Form(False),
    batch_size: int = Form(1000),
):
    """Upload and import a file."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    # Save uploaded file
    file_path = (
        UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    )

    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # For dry run, return immediately with preview
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
            "preview": (
                result.details.get("preview_rows", []) if result.details else []
            ),
            "columns": result.details.get("columns", []) if result.details else [],
            "mapping": result.details.get("mapping", {}) if result.details else {},
            "errors": result.errors,
            "log_file": result.log_file,
            "file_path": str(file_path),
        }

    # Background import for non-dry-run
    background_tasks.add_task(run_import)

    return {
        "status": "accepted",
        "message": "Import started in background",
        "supplier": supplier,
        "file_path": str(file_path),
        "file_name": file.filename,
    }


@app.get("/history")
async def get_history(supplier: Optional[str] = None, limit: int = 50):
    """Get import history."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    importer = get_importer()
    history = importer.get_import_history(supplier, limit)

    return {
        "total": len(history),
        "supplier": supplier or "all",
        "history": history,
    }


@app.get("/history/{audit_id}")
async def get_audit_detail(audit_id: int):
    """Get detailed audit record."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    with local_session() as session:
        from src.models import ImportAudit

        audit = session.query(ImportAudit).filter(ImportAudit.id == audit_id).first()

        if not audit:
            raise HTTPException(status_code=404, detail="Audit record not found")
        return audit.to_dict()


# ========== Suppliers API Endpoints ==========
@app.get("/api/suppliers")
async def api_get_suppliers():
    """Return list of all supplier names with mappings."""
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    mapper = get_mapper()
    suppliers = mapper.get_all_suppliers()

    return {
        "suppliers": suppliers,
        "total": len(suppliers),
    }


@app.get("/suppliers", response_class=HTMLResponse)
async def suppliers_list_page(request: Request):
    """Render suppliers list page."""
    if not templates:
        return HTMLResponse("Templates not found. Please check template directory.")

    return templates.TemplateResponse(
        request, "suppliers.html", {"request": request, "supplier": None}
    )


@app.get("/suppliers/{supplier_name}", response_class=HTMLResponse)
async def suppliers_page(request: Request, supplier_name: Optional[str] = None):
    """Render suppliers page with list and detail views."""
    if not templates:
        return HTMLResponse("Templates not found. Please check template directory.")

    return templates.TemplateResponse(
        request, "suppliers.html", {"request": request, "supplier": supplier_name}
    )


@app.post("/setup")
async def run_setup():
    """Run interactive setup via API."""
    config = get_config_manager()
    success = config.interactive_setup()

    if success:
        return {"status": "success", "message": "Setup completed successfully"}
    else:
        raise HTTPException(status_code=400, detail="Setup failed")


@app.get("/files/{file_path:path}")
async def download_file(file_path: str):
    """Download a file."""
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


from typing import List, Optional

from pydantic import BaseModel


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


@app.get("/schema", response_class=HTMLResponse)
async def schema_page(request: Request):
    """
    Render the schema viewer HTML page.
    Data is fetched separately via the /api/schema endpoint.
    """
    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    # Simply render the HTML template — no data processing here
    return templates.TemplateResponse(request, "schema.html", {"request": request})


@app.get("/api/schema")
async def api_schema(
    use_cache: bool = True,
    simplified: bool = False,
    refresh_cache: bool = False,
):
    """
    Return JSON schema for the default table.
    """

    if not ensure_configured():
        raise HTTPException(
            status_code=400, detail="Database not configured. Run setup first."
        )

    config = get_config_manager()
    default_products_table = config.get().default_products_table
    scanner = get_scanner()

    if refresh_cache:
        scanner.refresh_cache(default_products_table)

    if not scanner.table_exists(default_products_table):
        raise HTTPException(
            status_code=404,
            detail=f"Table '{default_products_table}' not found in the database.",
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


@app.post("/api/parse-sample")
async def parse_sample_file(file: UploadFile = File(...)):
    """Parse uploaded file and return column names + preview."""
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


@app.get("/add-supplier", response_class=HTMLResponse)
async def add_supplier_page(request: Request):
    """Render the add supplier mapping page."""
    if not templates:
        return HTMLResponse("Templates not found.")

    return templates.TemplateResponse(
        request, "add_supplier.html", {"request": request}
    )


def launch_web_ui():
    """Launch the FastAPI server and open browser."""
    import uvicorn

    # Check if configured
    config = get_config_manager()
    if not config.is_configured():
        print("🔐 Database not configured. Starting setup...")
        config.interactive_setup()
        if not config.is_configured():
            print("❌ Setup cancelled or failed. Exiting.")
            sys.exit(1)

    # Find available port
    port = find_available_port(8000)

    print(f"\n{'='*60}")
    print(f"🚀 MyFactory Import Tool - Web UI")
    print(f"{'='*60}")
    print(f"✅ Starting server at: http://127.0.0.1:{port}")
    print(f"📚 API docs at: http://127.0.0.1:{port}/docs")
    print(f"{'='*60}\n")

    # Start server in a separate thread
    def run_server():
        uvicorn.run("src.main:app", host="127.0.0.1", port=port, log_level="info")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to start
    time.sleep(2)

    # Open browser
    webbrowser.open(f"http://127.0.0.1:{port}")
    print("🌐 Browser opened to Web UI")
    print("Press Ctrl+C to stop the server\n")

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        sys.exit(0)
