"""
MyFactory Import Tool - CLI + API Entrypoint

CLI Usage:
    python main.py import --file path.csv --supplier ACME --dry-run
    python main.py list-mappings --supplier ACME
    python main.py setup

API Usage:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import argparse
import json
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text

# FastAPI imports (optional - only if available)
try:
    from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.templating import Jinja2Templates
    from starlette.requests import Request

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from src.config_manager import ensure_configured, get_config_manager
from src.db import get_db_manager, local_session
from src.importer import get_importer
from src.logger import get_logger
from src.mapper import get_mapper
from src.models import ImportStatus
from src.schema_scanner import get_scanner

logger = get_logger(__name__)


# ========== Helper Functions ==========


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


def launch_web_ui():
    """Launch the FastAPI server and open browser."""
    if not FASTAPI_AVAILABLE:
        print(
            "❌ FastAPI is not installed. Run: pip install fastapi uvicorn python-multipart"
        )
        sys.exit(1)

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


# ========== CLI Entrypoint ==========


def cli_import(args):
    """Import command: import file with supplier mapping."""

    if not ensure_configured():
        logger.error("Configuration not set up. Run 'python main.py setup' first.")
        sys.exit(1)

    logger.info(f"📁 Importing file: {args.file}")
    logger.info(f"🏷️ Supplier: {args.supplier}")
    logger.info(f"🔍 Dry run: {args.dry_run}")

    importer = get_importer()

    config = {
        "file_path": args.file,
        "supplier_name": args.supplier or "default",
        "dry_run": args.dry_run,
        "batch_size": args.batch or 1000,
        "table_name": args.table or "tdProducts",
        "delimiter": args.delimiter or None,
    }

    result = importer.import_file(config)

    # Print summary
    print("\n" + "=" * 70)
    print(f"📊 IMPORT SUMMARY")
    print("=" * 70)
    print(f"Status:        {result.status.value.upper()}")
    print(f"Total rows:    {result.total_rows}")
    print(f"✅ Imported:   {result.imported_rows}")
    print(f"❌ Failed:    {result.failed_rows}")
    print(f"⏭️ Skipped:   {result.skipped_rows}")
    print(f"Log file:      {result.log_file}")

    if result.errors:
        print(f"\n⚠️ Errors:")
        for error in result.errors[:5]:
            print(f"  - {error}")

    print("=" * 70)

    if result.status in [ImportStatus.SUCCESS, ImportStatus.DRY_RUN]:
        sys.exit(0)
    else:
        sys.exit(1)


def cli_list_mappings(args):
    """List mappings for a supplier."""
    if not ensure_configured():
        logger.error("Configuration not set up. Run 'python main.py setup' first.")
        sys.exit(1)

    mapper = get_mapper()

    if args.supplier:
        mappings = mapper.get_mappings(args.supplier)
        summary = mapper.get_mapping_summary(args.supplier)

        print(f"\n📋 Mappings for supplier: {args.supplier}")
        print("=" * 50)
        print(f"Total: {summary['total']}")
        print(f"Active: {summary['active']}")
        print(f"Inactive: {summary['inactive']}")
        print("=" * 50)

        if mappings:
            print(f"\n{'Source Field':<30} → {'Target Field':<30}")
            print("-" * 60)
            for source, target in mappings.items():
                print(f"{source:<30} → {target:<30}")
        else:
            print("\n⚠️ No mappings found for this supplier.")
    else:
        suppliers = mapper.get_all_suppliers()
        print(f"\n📋 All suppliers with mappings:")
        print("=" * 30)
        for s in suppliers:
            count = len(mapper.get_mappings(s))
            print(f"  {s}: {count} mappings")
        print("=" * 30)


def cli_save_mapping(args):
    """Save a mapping for a supplier."""
    if not ensure_configured():
        logger.error("Configuration not set up. Run 'python main.py setup' first.")
        sys.exit(1)

    mapper = get_mapper()
    mapper.save_mapping(args.supplier, args.source, args.target, args.active)
    print(f"✅ Mapping saved: {args.source} → {args.target} for {args.supplier}")


def cli_history(args):
    """Show import history."""
    if not ensure_configured():
        logger.error("Configuration not set up. Run 'python main.py setup' first.")
        sys.exit(1)

    importer = get_importer()
    history = importer.get_import_history(args.supplier, args.limit or 20)

    if not history:
        print("📋 No import history found.")
        return

    print(f"\n📋 Import History{' for ' + args.supplier if args.supplier else ''}")
    print("=" * 80)
    print(f"{'ID':<6} {'Date':<20} {'Status':<12} {'Rows':<8} {'File'}")
    print("-" * 80)

    for entry in history:
        date = entry["started_at"][:19] if entry["started_at"] else "N/A"
        status = entry["status"]
        rows = entry["rows_succeeded"]
        file_name = Path(entry.get("file_path", "")).name
        print(f"{entry['id']:<6} {date:<20} {status:<12} {rows:<8} {file_name}")

    print("=" * 80)


def cli_setup(args):
    """Run interactive setup."""
    config = get_config_manager()
    success = config.interactive_setup()
    if success:
        print("\n✅ Setup completed successfully!")
        print(config.get_config_summary())
    else:
        print("\n❌ Setup failed. Please try again.")
        sys.exit(1)


def cli_test_connection(args):
    """Test database connection."""
    config = get_config_manager()
    if not config.is_configured():
        print("❌ Configuration not set up. Run 'python main.py setup' first.")
        sys.exit(1)

    db = get_db_manager()
    if db.test_myfactory_connection():
        print("✅ Database connection successful!")
        print(f"   Server: {db.get_myfactory_server()}")
        print(f"   Database: {db.get_myfactory_database()}")

        # List tables
        try:
            tables = []
            with db.myfactory_session() as session:
                result = session.execute(
                    text(
                        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'"
                    )
                )
                tables = [row[0] for row in result.fetchall()]

            print(f"   Tables: {len(tables)} found")
            if args.verbose:
                print("   Sample tables:", ", ".join(tables[:10]))
        except Exception:
            pass
    else:
        print("❌ Database connection failed. Please check your credentials.")
        sys.exit(1)


def cli_clear_credentials(args):
    """Clear stored credentials."""
    config = get_config_manager()
    config.clear_credentials()
    print("✅ Credentials cleared.")


def cli_export_mappings(args):
    """Export mappings to JSON."""
    if not ensure_configured():
        logger.error("Configuration not set up. Run 'python main.py setup' first.")
        sys.exit(1)

    mapper = get_mapper()
    mappings = mapper.get_mappings(args.supplier)

    output = {
        "supplier": args.supplier,
        "exported_at": datetime.utcnow().isoformat(),
        "mappings": mappings,
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✅ Mappings exported to: {args.output}")
    else:
        print(json.dumps(output, indent=2))


# ========== CLI Parser ==========


def create_parser():
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="myfactory-import",
        description="MyFactory Import Tool - Import products from CSV/Excel to Myfactory CRM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import a file
  python main.py import --file data.csv --supplier ACME
  
  # Dry run (preview only)
  python main.py import --file data.csv --supplier ACME --dry-run
  
  # List mappings for a supplier
  python main.py list-mappings --supplier ACME
  
  # Save a mapping
  python main.py save-mapping --supplier ACME --source SKU
  
  # Show import history
  python main.py history --supplier ACME --limit 20
  
  # Run interactive setup
  python main.py setup
  
  # Start API server
  python main.py api --port 8000
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    subparsers.required = False  # Make optional for auto-UI

    # Import command
    import_parser = subparsers.add_parser("import", help="Import a file")
    import_parser.add_argument(
        "-f", "--file", required=True, help="Path to CSV/Excel file"
    )
    import_parser.add_argument(
        "-s", "--supplier", default="default", help="Supplier name"
    )
    import_parser.add_argument(
        "-d", "--dry-run", action="store_true", help="Dry run (preview only)"
    )
    import_parser.add_argument(
        "-b", "--batch", type=int, default=1000, help="Batch size"
    )
    import_parser.add_argument(
        "-t", "--table", default="tdProducts", help="Target table name"
    )
    import_parser.add_argument(
        "--delimiter", help="CSV delimiter (auto-detect if not specified)"
    )
    import_parser.set_defaults(func=cli_import)

    # List mappings
    list_parser = subparsers.add_parser(
        "list-mappings", help="List mappings for a supplier"
    )
    list_parser.add_argument(
        "-s", "--supplier", help="Supplier name (all if not specified)"
    )
    list_parser.set_defaults(func=cli_list_mappings)

    # Save mapping
    save_parser = subparsers.add_parser("save-mapping", help="Save a mapping")
    save_parser.add_argument("-s", "--supplier", required=True, help="Supplier name")
    save_parser.add_argument(
        "--source", required=True, help="Source field (CSV column)"
    )
    save_parser.add_argument(
        "--target", required=True, help="Target field (database column)"
    )
    save_parser.add_argument(
        "--active", action="store_true", default=True, help="Active status"
    )
    save_parser.set_defaults(func=cli_save_mapping)

    # History
    history_parser = subparsers.add_parser("history", help="Show import history")
    history_parser.add_argument(
        "-s", "--supplier", help="Supplier name (all if not specified)"
    )
    history_parser.add_argument(
        "-l", "--limit", type=int, default=20, help="Number of records to show"
    )
    history_parser.set_defaults(func=cli_history)

    # Setup
    setup_parser = subparsers.add_parser("setup", help="Run interactive setup")
    setup_parser.set_defaults(func=cli_setup)

    # Test connection
    test_parser = subparsers.add_parser(
        "test-connection", help="Test database connection"
    )
    test_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    test_parser.set_defaults(func=cli_test_connection)

    # Clear credentials
    clear_parser = subparsers.add_parser(
        "clear-credentials", help="Clear stored credentials"
    )
    clear_parser.set_defaults(func=cli_clear_credentials)

    # Export mappings
    export_parser = subparsers.add_parser(
        "export-mappings", help="Export mappings to JSON"
    )
    export_parser.add_argument("-s", "--supplier", required=True, help="Supplier name")
    export_parser.add_argument("-o", "--output", help="Output file path")
    export_parser.set_defaults(func=cli_export_mappings)

    # API command
    api_parser = subparsers.add_parser("api", help="Start API server")
    api_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)"
    )
    api_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind (default: 8000)"
    )
    api_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    api_parser.set_defaults(func=cli_api)

    # Schema command
    schema_parser = subparsers.add_parser("schema", help="Show table schema")
    schema_parser.add_argument("-t", "--table", default="tdProducts", help="Table name")
    schema_parser.add_argument(
        "--names-only", action="store_true", help="Show only column names"
    )
    schema_parser.add_argument("--refresh", action="store_true", help="Refresh cache")
    schema_parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show both tdProducts schemas",
    )
    schema_parser.set_defaults(func=cli_schema)
    return parser


def cli_api(args):
    """Start the API server."""
    if not FASTAPI_AVAILABLE:
        print(
            "❌ FastAPI is not installed. Run: pip install fastapi uvicorn python-multipart"
        )
        sys.exit(1)

    print(f"🚀 Starting API server at http://{args.host}:{args.port}")
    print(f"📚 API docs at http://{args.host}:{args.port}/docs")

    import uvicorn

    uvicorn.run("src.main:app", host=args.host, port=args.port, reload=args.reload)


def cli_schema(args):
    """Show table schema with rich formatting."""

    if not ensure_configured():
        logger.error("Configuration not set up. Run 'python main.py setup' first.")
        sys.exit(1)

    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console()
    scanner = get_scanner()

    if args.refresh:
        scanner.refresh_cache(args.table)
        console.print(f"[green]✅ Cache refreshed for {args.table}[/green]")
        return

    tables_to_scan = [args.table]
    for table_name in tables_to_scan:
        if not scanner.table_exists(table_name):
            console.print(f"[yellow]⚠️ Table '{table_name}' not found[/yellow]")
            continue

        if args.names_only:
            names = scanner.get_column_names(table_name)
            console.print(f"\n[bold cyan]📋 Columns in {table_name}:[/bold cyan]")
            for name in names:
                console.print(f"  • [green]{name}[/green]")
            console.print(f"\n[bold]Total: {len(names)} columns[/bold]")
            continue

        # Build Rich Table
        columns = scanner.get_table_schema(table_name)

        # Create table with box styling
        table = Table(
            title=f"[bold cyan]📊 Schema: {table_name}[/bold cyan]",
            box=box.HEAVY,
            border_style="bright_blue",
            show_header=True,
            header_style="bold magenta",
        )

        table.add_column("#", style="dim", width=4)
        table.add_column("Column Name", style="green", min_width=25)
        table.add_column("Data Type", style="yellow", min_width=20)
        table.add_column("Nullable", style="cyan", width=10)
        table.add_column("Primary Key", style="red", width=12)

        for idx, col in enumerate(columns, 1):
            nullable = "YES" if col.get("nullable", True) else "NO"
            table.add_row(str(idx), col.get("name", ""), col.get("type", ""), nullable)

        console.print("\n")
        console.print(table)
        console.print(f"[dim]Total: {len(columns)} columns[/dim]")
        console.print("\n" + "─" * 80 + "\n")


# ========== FastAPI Application ==========

if FASTAPI_AVAILABLE:
    from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from starlette.requests import Request

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

        # Import in background
        def run_import():
            importer = get_importer()
            result = importer.import_file(
                {
                    "file_path": str(file_path),
                    "supplier_name": supplier,
                    "dry_run": dry_run,
                    "batch_size": batch_size,
                }
            )
            return result

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

    # ========== Mappings API Endpoints ==========
    @app.get("/api/mappings/all")
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

    @app.get("/api/mappings/{supplier}")
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

    @app.post("/api/mappings/{supplier}")
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

    @app.delete("/api/mappings/{supplier}/{source_field}")
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

            audit = (
                session.query(ImportAudit).filter(ImportAudit.id == audit_id).first()
            )

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
                df = pd.read_csv(BytesIO(content))
            elif filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(BytesIO(content))
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
            raise HTTPException(
                status_code=400, detail=f"Failed to parse file: {str(e)}"
            )

    @app.get("/add-supplier", response_class=HTMLResponse)
    async def add_supplier_page(request: Request):
        """Render the add supplier mapping page."""
        if not templates:
            return HTMLResponse("Templates not found.")

        return templates.TemplateResponse(
            request, "add_supplier.html", {"request": request}
        )


# ========== Main Entrypoint ==========


def main():
    """Main entrypoint for CLI."""
    # If no arguments, launch Web UI
    if len(sys.argv) == 1:
        launch_web_ui()
        return
    parser = create_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
