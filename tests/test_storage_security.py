from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException

from app.storage import (
    OOXML_MAX_MEMBERS,
    OOXML_MAX_UNCOMPRESSED_BYTES,
    _validate_ooxml_archive,
    validate_upload_signature,
)


class FakeInfo:
    def __init__(self, filename: str, file_size: int = 1, flag_bits: int = 0):
        self.filename = filename
        self.file_size = file_size
        self.flag_bits = flag_bits


class FakeArchive:
    def __init__(self, infos, bad_member=None):
        self._infos = infos
        self._bad_member = bad_member

    def infolist(self):
        return list(self._infos)

    def testzip(self):
        return self._bad_member


def make_minimal_ooxml(extension: str) -> bytes:
    out = io.BytesIO()
    required = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr(required, "<root>PlaceAI</root>")
    return out.getvalue()


def test_valid_minimal_ooxml_packages_are_accepted():
    assert validate_upload_signature(make_minimal_ooxml(".docx"), ".docx").startswith("application/")
    assert validate_upload_signature(make_minimal_ooxml(".xlsx"), ".xlsx").startswith("application/")


def test_ooxml_rejects_excessive_member_count_before_decompression():
    infos = [FakeInfo("[Content_Types].xml"), FakeInfo("word/document.xml")]
    infos.extend(FakeInfo(f"word/media/item-{index}.bin") for index in range(OOXML_MAX_MEMBERS))
    with pytest.raises(ValueError, match="too many"):
        _validate_ooxml_archive(FakeArchive(infos), ".docx")


def test_ooxml_rejects_excessive_expanded_size_before_decompression():
    infos = [
        FakeInfo("[Content_Types].xml", 1),
        FakeInfo("word/document.xml", OOXML_MAX_UNCOMPRESSED_BYTES + 1),
    ]
    with pytest.raises(ValueError, match="expands beyond"):
        _validate_ooxml_archive(FakeArchive(infos), ".docx")


def test_ooxml_rejects_encrypted_members_and_crc_failures():
    encrypted = [FakeInfo("[Content_Types].xml"), FakeInfo("word/document.xml", flag_bits=0x1)]
    with pytest.raises(ValueError, match="encrypted"):
        _validate_ooxml_archive(FakeArchive(encrypted), ".docx")

    normal = [FakeInfo("[Content_Types].xml"), FakeInfo("word/document.xml")]
    with pytest.raises(ValueError, match="CRC failure"):
        _validate_ooxml_archive(FakeArchive(normal, bad_member="word/document.xml"), ".docx")


def test_ooxml_public_validator_rejects_missing_canonical_members():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("not-word/document.xml", "<root></root>")

    with pytest.raises(HTTPException) as exc:
        validate_upload_signature(out.getvalue(), ".docx")
    assert exc.value.status_code == 400
