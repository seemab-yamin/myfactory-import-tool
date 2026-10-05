import tempfile
from datetime import datetime
from pathlib import Path

import aiofiles
from fastapi import (
    HTTPException,
    UploadFile,
)

# Upload directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


async def validate_file(file: UploadFile):
    # ✅ Validate file type (.csv, .xlsx, .xls)
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ✅ Validate file size
    file_size = 0
    try:
        content = await file.read()
        file_size = len(content)
        await file.seek(0)  # Reset file pointer for later use
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    if file_size == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    return file  # Return the validated file for further processing


async def get_file_path(file: UploadFile, upload_dir: Path = UPLOAD_DIR) -> Path:
    # ✅ Save uploaded file to UPLOAD_DIR with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{Path(file.filename).name}"
    file_path = upload_dir / safe_filename
    return file_path


async def save_file(file: UploadFile, file_path: Path):
    try:
        file_size = 0
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024 * 1024)} MB",
                    )
                await f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")


async def save_file_temp(file: UploadFile):
    # Determine file type
    filename = file.filename.lower()
    suffix = Path(filename).suffix

    await validate_file(file=file)  # Validate file type and size

    content = await file.read()
    # write to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(content)
        tmp_file_path = tmp_file.name

    return tmp_file_path
