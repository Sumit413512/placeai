from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_institution_admin
from app.models import Application, Job, Offer, RecruiterProfile, StudentProfile, User
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


def _institution_report_rows(org_id: str, kind: str, db: Session) -> tuple[list[str], list[list[Any]]]:
    """Return report rows whose company/job evidence actually belongs to this institution.

    Public jobs are platform-wide. They belong in an institution participation report only
    after one of that institution's students applies. Campus-targeted jobs are included even
    before the first application. Other report kinds retain the established report builder.
    """
    if kind not in {"company-participation", "recruiter-activity"}:
        return _report_rows(org_id, kind, db)

    student_ids = [
        row[0]
        for row in db.query(StudentProfile.id).filter(StudentProfile.organization_id == org_id).all()
    ]
    applications = (
        db.query(Application).filter(Application.student_id.in_(student_ids)).all()
        if student_ids else []
    )
    applied_job_ids = {application.job_id for application in applications if application.job_id}

    relevant_jobs = db.query(Job).filter(Job.target_organization_id == org_id).all()
    relevant_job_ids = {job.id for job in relevant_jobs}
    missing_applied_ids = applied_job_ids - relevant_job_ids
    if missing_applied_ids:
        relevant_jobs.extend(db.query(Job).filter(Job.id.in_(missing_applied_ids)).all())
        relevant_job_ids.update(missing_applied_ids)

    application_count_by_job: dict[str, int] = {}
    for application in applications:
        if application.job_id in relevant_job_ids:
            application_count_by_job[application.job_id] = application_count_by_job.get(application.job_id, 0) + 1

    if kind == "company-participation":
        company: dict[str, dict[str, int]] = {}
        for job in relevant_jobs:
            name = job.recruiter.company_name if job.recruiter and job.recruiter.company_name else "Company"
            bucket = company.setdefault(name, {"jobs": 0, "applications": 0, "offers": 0})
            bucket["jobs"] += 1
            bucket["applications"] += application_count_by_job.get(job.id, 0)

        offers = (
            db.query(Offer)
            .join(Application, Offer.application_id == Application.id)
            .filter(Application.student_id.in_(student_ids))
            .all()
            if student_ids else []
        )
        for offer in offers:
            name = offer.company_name or "Company"
            company.setdefault(name, {"jobs": 0, "applications": 0, "offers": 0})["offers"] += 1

        headers = ["Company", "Jobs / drives", "Applications", "Offers"]
        rows = [
            [name, values["jobs"], values["applications"], values["offers"]]
            for name, values in sorted(company.items(), key=lambda item: item[0].lower())
        ]
        return headers, rows

    recruiter_ids = {
        row[0]
        for row in db.query(RecruiterProfile.id).filter(
            RecruiterProfile.provisioned_by_organization_id == org_id
        ).all()
    }
    recruiter_ids.update(job.recruiter_id for job in relevant_jobs if job.recruiter_id)
    recruiters = (
        db.query(RecruiterProfile).filter(RecruiterProfile.id.in_(recruiter_ids)).all()
        if recruiter_ids else []
    )
    jobs_by_recruiter: dict[str, list[Job]] = {}
    for job in relevant_jobs:
        if job.recruiter_id:
            jobs_by_recruiter.setdefault(job.recruiter_id, []).append(job)

    headers = [
        "Company",
        "Recruiter",
        "Verified",
        "Jobs",
        "Applications",
        "Successful placements",
        "Verification confidence",
    ]
    rows = []
    for recruiter in sorted(recruiters, key=lambda item: (item.company_name or "").lower()):
        recruiter_jobs = jobs_by_recruiter.get(recruiter.id, [])
        app_count = sum(application_count_by_job.get(job.id, 0) for job in recruiter_jobs)
        rows.append([
            recruiter.company_name,
            recruiter.full_name,
            "Yes" if recruiter.is_verified else "No",
            len(recruiter_jobs),
            app_count,
            recruiter.previous_successful_placements,
            recruiter.company_verification_confidence,
        ])
    return headers, rows


@router.get("/reports/{kind}.{fmt}")
def export_report_safe(
    kind: str,
    fmt: str,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    """Export institution-scoped reports with spreadsheet-formula neutralization."""
    org = _org_for_user(current_user, db)
    headers, rows = _institution_report_rows(org.id, kind, db)
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
        _width, height = A4
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
