from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_institution_admin
from app.models import User
from app.routers.enterprise import _org_for_user, _report_rows

router = APIRouter(prefix="/enterprise", tags=["Enterprise Placement Operations"])

_DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@")
_LEADING_CONTROL_CHARS = ("\t", "\r", "\n")


def spreadsheet_safe_cell(value: Any) -> Any:
    """Neutralize spreadsheet formula execution while preserving non-string values.

    CSV and XLSX consumers such as Excel may interpret attacker-controlled text beginning
    with formula markers as executable formulas. Prefix risky strings with an apostrophe,
    including values where spaces/control characters precede the formula marker.
    """
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" \t\r\n")
    if value.startswith(_LEADING_CONTROL_CHARS) or stripped.startswith(_DANGEROUS_FORMULA_PREFIXES):
        return "'" + value
    return value


def _safe_rows(rows: list[list[Any]]) -> list[list[Any]]:
    return [[spreadsheet_safe_cell(cell) for cell in row] for row in rows]


@router.get("/reports/{kind}.{fmt}")
def export_report_safe(
    kind: str,
    fmt: str,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    """Export institution-scoped reports with spreadsheet-formula neutralization."""
    org = _org_for_user(current_user, db)
    headers, rows = _report_rows(org.id, kind, db)
    fmt = fmt.lower()

    if fmt == "csv":
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(headers)
        writer.writerows(_safe_rows(rows))
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{kind}.csv"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    if fmt == "xlsx":
        try:
            from openpyxl import Workbook
        except Exception as exc:
            raise HTTPException(status_code=503, detail="XLSX export dependency unavailable") from exc
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "PlaceAI Report"
        worksheet.append(headers)
        for row in _safe_rows(rows):
            worksheet.append(row)
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{kind}.xlsx"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    if fmt == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except Exception as exc:
            raise HTTPException(status_code=503, detail="PDF export dependency unavailable") from exc
        output = io.BytesIO()
        pdf = canvas.Canvas(output, pagesize=A4)
        width, height = A4
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(36, height - 40, f"{org.name} — {kind.replace('-', ' ').title()}")
        y = height - 68
        pdf.setFont("Helvetica", 8)
        pdf.drawString(36, y, " | ".join(headers))
        y -= 16
        for row in rows:
            line = " | ".join("" if cell is None else str(cell) for cell in row)
            pdf.drawString(36, y, line[:115])
            y -= 12
            if y < 40:
                pdf.showPage()
                y = height - 40
                pdf.setFont("Helvetica", 8)
        pdf.save()
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{kind}.pdf"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    raise HTTPException(status_code=400, detail="Format must be csv, xlsx or pdf")
