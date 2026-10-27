from typing import Optional

from fastapi import Body, File, Form, UploadFile
from pydantic import constr

from src.schemas.base import StrictRequestModel


class ParseSample(StrictRequestModel):
    file: UploadFile = File(...)
    delimiter: Optional[str] = Form(None)
    header_row_index: int = Form(1)
    sheet_name: Optional[str] = Form(None)


class SaveMappingsRequest(StrictRequestModel):
    source_fields: list[str] = None
    mappings: Optional[list[dict]] = None
    is_new_supplier: bool = Body(False)
    delimiter: Optional[str] = None
    header_row_index: int = Form(1)
    sheet_name: Optional[str] = None
    memo: Optional[constr(max_length=1000)] = None


class UploadRequest(StrictRequestModel):
    file: UploadFile = File(...)
    supplier_id: int = Form(...)
    dry_run: bool = Form(False)
    batch_size: int = Form(1000)
    delimiter: Optional[str] = None
    header_row_index: int = Form(1)
    sheet_name: Optional[str] = None
