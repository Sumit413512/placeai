"""Shared print layout for every student opportunity guide."""
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.opportunity_insights import _host

INK = "#26231F"
BURGUNDY = "#732B3D"
MUTED = "#514940"


def render_guide(guide: dict) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=46, rightMargin=46, topMargin=57, bottomMargin=54,
        title=f"Interview preparation | {guide['role']}", author="PlaceAI",
    )
    body = ParagraphStyle("Body", fontName="Helvetica", fontSize=11, leading=16, textColor=INK,
                          spaceAfter=9, splitLongWords=True)
    styles = {
        "body": body,
        "bullet": ParagraphStyle("Bullet", parent=body, leftIndent=13, bulletIndent=0),
        "title": ParagraphStyle("Title", parent=body, fontName="Helvetica-Bold", fontSize=28,
                                leading=33, textColor=BURGUNDY, keepWithNext=True),
        "heading": ParagraphStyle("Heading", parent=body, fontName="Helvetica-Bold", fontSize=16,
                                  leading=21, textColor=BURGUNDY, spaceBefore=17, keepWithNext=True),
        "sub": ParagraphStyle("Subheading", parent=body, fontName="Helvetica-Bold", spaceBefore=5,
                              keepWithNext=True),
        "muted": ParagraphStyle("Context", parent=body, textColor=MUTED),
    }
    story = []

    def add(value: str, style: str = "body") -> None:
        story.append(Paragraph(escape(value).replace("\n", "<br/>"), styles[style]))

    def section(title: str) -> None:
        add(title, "heading")

    def rows(items: list[str]) -> None:
        for item in items:
            story.append(Paragraph(escape(item), styles["bullet"], bulletText="•"))

    def source_link(url: str) -> None:
        if _host(url) and not any(char.isspace() for char in url):
            story.append(Paragraph(f"<link href={quoteattr(url)} color={quoteattr(BURGUNDY)}>"
                                   f"{escape(_host(url))} • Open source</link>", body))

    add(guide["role"], "title")
    add(guide["company"])
    add("Interview preparation guide · " + date.today().isoformat(), "muted")
    if guide["demo"]:
        add("Fictional demonstration. Company and hiring details are illustrative.", "muted")
    elif not guide["tailored"]:
        add("Posting-based study guide. AI-tailored practice was unavailable for this download.", "muted")
    story.append(Spacer(1, 4))

    section("1. Company and role")
    if guide["industry"]:
        add(f"Industry · {guide['industry']}")
    if guide["about"]:
        add(guide["about"])
    source_link(guide["website"])
    add("From the published job description", "sub")
    add(guide["description"] or "The posting did not include a job description.")
    if guide["skills"]:
        add("Required skills", "sub")
        add(", ".join(guide["skills"]))

    prep = guide["preparation"]
    section("2. What to study first")
    rows(prep.priorities)

    section("3. Round-by-round preparation")
    add("Round order comes from the campus posting." if guide["published_rounds"] else
        "Suggested practice sequence. Confirm the actual rounds with your placement office.", "muted")
    for index, (name, steps) in enumerate(zip(guide["rounds"], prep.rounds, strict=True), 1):
        add(f"{index}. {name}", "sub")
        rows(steps)

    section("4. Practice questions and answer approaches")
    add("Use these original practice questions to rehearse.", "muted")
    for item in prep.questions:
        add(item.question, "sub")
        add(item.approach)

    section("5. Study plan and interview day")
    rows(prep.study_plan)
    add("Check the official schedule, venue or meeting link, and required documents before interview day.")

    section("6. Sources and public interview accounts")
    add("Primary source · The PlaceAI opportunity and its published selection stages.")
    if guide["search_note"]:
        add(guide["search_note"], "muted")
    if guide["evidence"]:
        add("Public accounts may reflect a different hiring cycle. Confirm this drive’s process with the placement office.", "muted")
    for index, item in enumerate(guide["evidence"], 1):
        add(f"{index}. {item['title']}", "sub")
        add(f"{item['kind']} · {item['excerpt']}")
        source_link(item["url"])

    def decorate(canvas, doc) -> None:
        width, height = A4
        canvas.setFillColor(colors.HexColor(BURGUNDY))
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(doc.leftMargin, height - 35, "PlaceAI  /  Interview preparation")
        canvas.setStrokeColor(colors.HexColor("#DED2C4"))
        canvas.line(doc.leftMargin, height - 43, width - doc.rightMargin, height - 43)
        canvas.line(doc.leftMargin, 43, width - doc.rightMargin, 43)
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(doc.leftMargin, 28, "PlaceAI · Student workspace")
        canvas.drawRightString(width - doc.rightMargin, 28, f"Page {doc.page}")

    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()
