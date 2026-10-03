from typing import List, Optional

from fastapi import Body, File, Form, UploadFile

from src.schemas.base import StrictRequestModel


class ParseSample(StrictRequestModel):
    file: UploadFile = File(...)
    delimiter: Optional[str] = Form(None)
    header_row_index: int = Form(1)
    sheet_name: Optional[str] = Form(None)


class SaveMappingsRequest(StrictRequestModel):
    source_fields: List[str] = (Body(...),)
    mappings: List[dict] = (Body(...),)
    is_new_supplier: bool = (Body(False),)
    delimiter: Optional[str] = (Body(None),)
    header_row_index: int = (Body(1),)
    sheet_name: Optional[str] = (Body(None),)


class UploadRequest(StrictRequestModel):
    file: UploadFile = File(...)
    supplier_id: int = Form(...)
    dry_run: bool = Form(False)
    batch_size: int = Form(1000)
    header_row_index: int = Form(1)
    sheet_name: str = Form(None)
