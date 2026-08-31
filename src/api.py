from fastapi import Form, HTTPException

from src.config_manager import ensure_configured
from src.logger import get_logger
from src.mapper import get_mapper

logger = get_logger(__name__)

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
