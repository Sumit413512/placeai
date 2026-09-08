from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import StoredFile

settings = get_settings()
DB_PREFIX = "dbfile:"

_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def database_storage_enabled() -> bool:
    return settings.uses_database_file_storage


def safe_upload_filename(filename: str | None, fallback: str = "file") -> str:
    # Browsers normally submit basenames, but never trust client supplied path segments.
    name = Path((filename or fallback).replace("\\", "/")).name.strip()
    return (name or fallback)[:300]


def trusted_mime_type(extension: str, fallback: str = "application/octet-stream") -> str:
    return _MIME_BY_EXTENSION.get(extension.lower(), fallback)


def validate_upload_signature(data: bytes, extension: str) -> str:
    """Validate file content against its extension and return a server-trusted MIME type.

    This is deliberately conservative. Legacy OLE Office formats (.doc/.xls) are rejected;
    modern Office documents must be valid ZIP containers with the expected package member.
    Text uploads must be UTF-8 and may not contain NUL bytes.
    """
    ext = extension.lower()
    if ext not in _MIME_BY_EXTENSION:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF")
    elif ext == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=400, detail="The uploaded file is not a valid PNG image")
    elif ext in {".jpg", ".jpeg"}:
        if not data.startswith(b"\xff\xd8\xff"):
            raise HTTPException(status_code=400, detail="The uploaded file is not a valid JPEG image")
    elif ext in {".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                # Reject malformed/ambiguous archives and require the canonical OOXML payload.
                archive.testzip()
                required = "word/document.xml" if ext == ".docx" else "xl/workbook.xml"
                if required not in names or "[Content_Types].xml" not in names:
                    raise ValueError("missing Office package members")
        except (zipfile.BadZipFile, RuntimeError, ValueError):
            label = "Word" if ext == ".docx" else "Excel"
            raise HTTPException(status_code=400, detail=f"The uploaded file is not a valid {label} document")
    elif ext in {".csv", ".txt"}:
        if b"\x00" in data:
            raise HTTPException(status_code=400, detail="Text uploads may not contain binary NUL bytes")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Text uploads must be UTF-8 encoded")

    return trusted_mime_type(ext)


def save_file(
    db: Session,
    *,
    category: str,
    original_filename: str,
    mime_type: str | None,
    data: bytes,
    local_path: Path,
) -> str:
    if database_storage_enabled():
        record = StoredFile(
            category=category[:120],
            original_filename=safe_upload_filename(original_filename),
            mime_type=(mime_type or "application/octet-stream")[:160],
            size_bytes=len(data),
            data=data,
        )
        db.add(record)
        db.flush()
        return f"{DB_PREFIX}{record.id}"

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data)
    return str(local_path)


def _stored_record(db: Session, reference: str) -> StoredFile | None:
    if not reference.startswith(DB_PREFIX):
        return None
    file_id = reference[len(DB_PREFIX):]
    return db.query(StoredFile).filter(StoredFile.id == file_id).first()


def read_file_bytes(db: Session, reference: str) -> bytes | None:
    record = _stored_record(db, reference)
    if reference.startswith(DB_PREFIX):
        return bytes(record.data) if record else None
    path = Path(reference)
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def delete_file(db: Session, reference: str | None) -> None:
    if not reference:
        return
    record = _stored_record(db, reference)
    if reference.startswith(DB_PREFIX):
        if record:
            db.delete(record)
        return
    try:
        Path(reference).unlink(missing_ok=True)
    except OSError:
        pass


def file_download_response(
    db: Session,
    reference: str | None,
    *,
    filename: str,
    media_type: str = "application/octet-stream",
):
    if not reference:
        raise HTTPException(status_code=404, detail="File not found")
    record = _stored_record(db, reference)
    if reference.startswith(DB_PREFIX):
        if not record:
            raise HTTPException(status_code=404, detail="File not found")
        safe_name = quote(safe_upload_filename(filename or record.original_filename or "download"))
        return Response(
            content=bytes(record.data),
            media_type=media_type or record.mime_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}",
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    path = Path(reference)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        media_type=media_type,
        filename=safe_upload_filename(filename),
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
