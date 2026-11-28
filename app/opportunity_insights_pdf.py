"""Professional multi-page PDF layout for PlaceAI interview intelligence dossiers."""
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.opportunity_insights import _host

INK = "#27221F"
BURGUNDY = "#6F263D"
BURGUNDY_DARK = "#4C1829"
SAND = "#F3ECE2"
CREAM = "#FBF8F3"
MUTED = "#5F574F"
LINE = "#D8CBBE"
GREEN = "#2F654D"
AMBER = "#8A5A17"


def render_guide(guide: dict) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title=f"Company and interview intelligence | {guide['role']} | {guide['company']}",
        author="PlaceAI",
        subject="Evidence-aware company and role preparation dossier",
    )
    body = ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=10.4, leading=15, textColor=INK,
        spaceAfter=7, splitLongWords=True,
    )
    styles = {
        "body": body,
        "bullet": ParagraphStyle("Bullet", parent=body, leftIndent=12, firstLineIndent=-8, spaceAfter=6),
        "small": ParagraphStyle("Small", parent=body, fontSize=9.2, leading=13, textColor=MUTED),
        "title": ParagraphStyle(
            "Title", parent=body, fontName="Helvetica-Bold", fontSize=27, leading=32,
            textColor=BURGUNDY_DARK, spaceAfter=7,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub", parent=body, fontName="Helvetica-Bold", fontSize=14, leading=19,
            textColor=BURGUNDY,
        ),
        "section": ParagraphStyle(
            "Section", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=22,
            textColor=BURGUNDY, spaceBefore=5, spaceAfter=10, keepWithNext=True,
        ),
        "sub": ParagraphStyle(
            "Sub", parent=body, fontName="Helvetica-Bold", fontSize=11.4, leading=15,
            textColor=INK, spaceBefore=6, spaceAfter=4, keepWithNext=True,
        ),
        "label": ParagraphStyle(
            "Label", parent=body, fontName="Helvetica-Bold", fontSize=8.8, leading=11,
            textColor=BURGUNDY, spaceAfter=2,
        ),
        "card": ParagraphStyle("Card", parent=body, fontSize=10, leading=14, spaceAfter=0),
        "quote": ParagraphStyle(
            "Quote", parent=body, fontName="Helvetica-Oblique", fontSize=10.2,
            leading=15, leftIndent=8, rightIndent=8, textColor=MUTED,
        ),
        "center": ParagraphStyle("Center", parent=body, alignment=TA_CENTER),
    }
    story = []
    prep = guide["preparation"]

    def p(value: str, style: str = "body") -> Paragraph:
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def add(value: str, style: str = "body") -> None:
        story.append(p(value, style))

    def heading(title: str, subtitle: str = "") -> None:
        story.append(Paragraph(escape(title), styles["section"]))
        if subtitle:
            story.append(Paragraph(escape(subtitle), styles["small"]))

    def bullets(items: list[str], checkbox: bool = False) -> None:
        marker = "[ ]" if checkbox else "-"
        for item in items:
            story.append(Paragraph(f"{marker} {escape(str(item))}", styles["bullet"]))

    def refs(source_ids: list[str]) -> str:
        return f" [{', '.join(source_ids)}]" if source_ids else ""

    def insight_cards(items) -> None:
        for item in items:
            label = item.confidence.upper()
            color = GREEN if item.confidence in {"confirmed", "supported"} else AMBER if item.confidence == "indicative" else BURGUNDY
            card = Table(
                [[Paragraph(f"<font color='{color}'><b>{escape(label)}</b></font>", styles["label"]),
                  Paragraph(escape(item.text) + escape(refs(item.source_ids)), styles["card"])]],
                colWidths=[27 * mm, 143 * mm],
            )
            card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(CREAM)),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            story.extend([card, Spacer(1, 5)])

    def question_cards(items) -> None:
        for index, item in enumerate(items, 1):
            signals = " / ".join(item.strong_answer_signals) if item.strong_answer_signals else "Evidence / clarity / structure"
            block = [
                p(f"{index}. {item.question}", "sub"),
                p(item.approach, "body"),
                Paragraph(f"<b>Strong answer signals:</b> {escape(signals)}", styles["small"]),
            ]
            story.append(KeepTogether(block))
            story.append(Spacer(1, 4))

    def new_page() -> None:
        story.append(PageBreak())

    # Cover
    add("PLACEAI / COMPANY AND ROLE INTELLIGENCE", "label")
    story.append(Spacer(1, 16))
    add(guide["role"], "title")
    add(guide["company"], "cover_sub")
    story.append(Spacer(1, 12))
    badge = "FICTIONAL DEMONSTRATION" if guide["demo"] else "EVIDENCE-AWARE RESEARCH DOSSIER"
    badge_table = Table([[p(badge, "label")]], colWidths=[70 * mm])
    badge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SAND)),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(BURGUNDY)),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(badge_table)
    story.append(Spacer(1, 15))
    snapshot = [
        [p("Generated", "label"), p(date.today().isoformat(), "card")],
        [p("Research depth", "label"), p(guide["research_depth"], "card")],
        [p("Public sources", "label"), p(str(len(guide["evidence"])), "card")],
        [p("Role skills", "label"), p(str(len(guide["skills"])), "card")],
        [p("Selection stages", "label"), p(str(len(guide["rounds"])), "card")],
        [p("AI synthesis", "label"), p("Completed" if guide["tailored"] else "Safe baseline", "card")],
    ]
    summary_table = Table(snapshot, colWidths=[48 * mm, 118 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(SAND)),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor(CREAM)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 15))
    if guide["demo"]:
        add("This sample uses a fictional employer. It demonstrates the full preparation structure without claiming real company history.", "quote")
    elif not guide["tailored"]:
        add("Posting-based study guide. AI-tailored synthesis was unavailable, so PlaceAI used the safe preparation baseline.", "quote")
    else:
        add("Use this dossier to prepare, then confirm current instructions with the employer and your placement office.", "quote")
    story.append(Spacer(1, 20))
    add("Evidence standard", "sub")
    bullets([
        "Confirmed - from the posting or an official company source.",
        "Supported - consistent with cited public evidence.",
        "Indicative - useful direction, not a guaranteed current fact.",
        "Practice - PlaceAI coaching or an original rehearsal question.",
    ])

    # Executive briefing and company
    new_page()
    heading("1. Executive briefing", "What matters most before you begin preparation.")
    bullets(prep.executive_summary)
    add("Priority actions", "sub")
    bullets(prep.priorities)
    heading("2. Company intelligence", "Business context, products, and evidence-backed company understanding.")
    if guide["industry"]:
        add(f"Industry: {guide['industry']}")
    if guide["about"]:
        add(guide["about"])
    if guide["website"] and _host(guide["website"]):
        story.append(Paragraph(
            f"<link href={quoteattr(guide['website'])} color={quoteattr(BURGUNDY)}>"
            f"Official website: {escape(_host(guide['website']))}</link>",
            styles["body"],
        ))
    insight_cards(prep.company_intelligence)
    add("Business and product context", "sub")
    insight_cards(prep.business_and_products)

    # Role and competency matrix
    new_page()
    heading("3. Role decoding", "Translate the job description into outcomes you must prove.")
    add("Published role description", "sub")
    add(guide["description"] or "The opportunity did not include a detailed job description.")
    if guide["skills"]:
        add("Published or extracted skills", "sub")
        add(", ".join(guide["skills"]))
    add("Expected outcomes", "sub")
    bullets(prep.role_outcomes)
    add("Competency matrix", "sub")
    rows = [[p("Competency", "label"), p("Why it matters", "label"), p("Target and preparation", "label")]]
    for item in prep.competencies:
        rows.append([
            p(item.skill + refs(item.source_ids), "card"),
            p(item.why_it_matters, "card"),
            p(item.target_level + "\n" + item.preparation, "card"),
        ])
    matrix = LongTable(rows, colWidths=[36 * mm, 59 * mm, 75 * mm], repeatRows=1)
    matrix.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BURGUNDY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(CREAM), colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(matrix)

    # Stack and historical patterns
    new_page()
    heading("4. Engineering context and technology stack", "Only cited or posting-derived signals are treated as company-specific.")
    insight_cards(prep.engineering_and_stack)
    add("How to use stack information", "sub")
    bullets([
        "Prioritise technologies named in the job description.",
        "Use official engineering sources as company context, not proof that every team uses the same stack.",
        "Prepare transferable fundamentals: data structures, APIs, databases, testing, security, debugging, and delivery.",
        "Be ready to explain how you would learn an unfamiliar tool during the first weeks.",
    ])
    heading("5. Interview history and reported patterns", "Public accounts are directional and may represent another team or hiring cycle.")
    if prep.historical_patterns:
        for item in prep.historical_patterns:
            add(f"{item.stage} / {item.period} {refs(item.source_ids)}", "sub")
            add(item.reported_pattern)
            if item.reported_questions:
                add("Questions or themes reported in the cited account", "label")
                bullets(item.reported_questions)
    else:
        add("No role-matched public interview account passed the evidence checks for this dossier.")
        bullets([
            "Ask the placement office whether the current drive has an assessment, coding round, technical panels, or HR round.",
            "Use the original practice questions in this dossier without assuming they were previously asked by the employer.",
        ])

    # Rounds
    new_page()
    heading("6. Round-by-round strategy", "A preparation workflow from assessment to final conversation.")
    add(
        "Round order comes from the campus posting."
        if guide["published_rounds"]
        else "This is a suggested practice sequence. Confirm the current process with the placement office.",
        "small",
    )
    for index, (name, steps) in enumerate(zip(guide["rounds"], prep.rounds, strict=True), 1):
        block = [p(f"Round {index} - {name}", "sub")]
        block.extend(Paragraph(f"- {escape(step)}", styles["bullet"]) for step in steps)
        story.append(KeepTogether(block))
        story.append(Spacer(1, 7))

    # Technical questions
    new_page()
    heading("7. Technical rehearsal bank", "Original practice prompts unless a historical source is explicitly cited.")
    question_cards(prep.technical_questions)

    # Behavioural and HR
    new_page()
    heading("8. Behavioural interview", "Use STAR: Situation, Task, Action, Result, then Reflection.")
    question_cards(prep.behavioral_questions)
    new_page()
    heading("9. HR conversation and role fit", "Sound specific, honest, and evidence-based.")
    question_cards(prep.hr_playbook)
    add("Your 60-90 second introduction", "sub")
    add(prep.self_introduction, "quote")
    add("Project deep-dive structure", "sub")
    add(prep.project_pitch, "quote")

    # Communication and plan
    new_page()
    heading("10. Communication and professional presence", "How to think, speak, and present yourself under interview pressure.")
    bullets(prep.communication_coaching)
    add("Questions to ask the interviewer", "sub")
    bullets(prep.questions_to_ask)
    heading("11. Seven-day preparation plan")
    bullets(prep.study_plan, checkbox=True)
    new_page()
    heading("12. Interview-day checklist")
    bullets(prep.interview_day_checklist, checkbox=True)
    add("Important risk controls", "sub")
    bullets(prep.risk_flags)

    # Sources
    new_page()
    heading("13. Sources and evidence notes", "Source ids are referenced throughout this dossier.")
    add("Primary source: the PlaceAI opportunity record, job description, required skills, and published selection stages.")
    add(guide["search_note"], "small")
    if guide["evidence"]:
        add("Third-party accounts can be incomplete or outdated. They are clearly marked and must not be treated as official.", "small")
    for item in guide["evidence"]:
        add(f"{item['id']} - {item['title']}", "sub")
        meta = item["kind"]
        if item.get("published_date"):
            meta += f" / {item['published_date']}"
        add(meta, "label")
        add(item["excerpt"], "small")
        if _host(item["url"]):
            story.append(Paragraph(
                f"<link href={quoteattr(item['url'])} color={quoteattr(BURGUNDY)}>"
                f"{escape(_host(item['url']))} - Open source</link>",
                styles["body"],
            ))
    add("Final verification", "sub")
    bullets([
        "Confirm the current round sequence and eligibility with the placement office.",
        "Confirm company facts that may change, including locations, products, leadership, and technology.",
        "Use reported questions as preparation signals, not as a promised question set.",
        "Update your answers with truthful evidence from your own projects and experience.",
    ])

    def decorate(canvas, doc) -> None:
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(BURGUNDY))
        canvas.rect(0, height - 7, width, 7, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.setFillColor(colors.HexColor(BURGUNDY_DARK))
        canvas.drawString(doc.leftMargin, height - 35, "PlaceAI / Interview intelligence")
        canvas.setStrokeColor(colors.HexColor(LINE))
        canvas.line(doc.leftMargin, height - 42, width - doc.rightMargin, height - 42)
        canvas.line(doc.leftMargin, 41, width - doc.rightMargin, 41)
        canvas.setFont("Helvetica", 8.8)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(doc.leftMargin, 27, f"{guide['company']} / {guide['role']}")
        canvas.drawRightString(width - doc.rightMargin, 27, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()

