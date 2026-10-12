"""Readable A4 teaching notes with vector diagrams, wrapped code and linked references."""
from __future__ import annotations

import io
import re
from html import escape
from pathlib import Path
from textwrap import wrap

import reportlab
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                                Preformatted)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon

ACCENT = colors.HexColor("#59416f")
INK = colors.HexColor("#272330")


def _fonts():
    font_root = Path(reportlab.__file__).parent / "fonts"
    if "LearningSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("LearningSans", str(font_root / "Vera.ttf")))



def _label_lines(label, size, width):
    lines = []
    for line in simpleSplit(label, "LearningSans", size, width):
        while pdfmetrics.stringWidth(line, "LearningSans", size) > width:
            end = 1
            while end < len(line) and pdfmetrics.stringWidth(line[:end + 1], "LearningSans", size) <= width:
                end += 1
            lines.append(line[:end])
            line = line[end:]
        if line:
            lines.append(line)
    return lines


def diagram_rows(diagram, width=490):
    labels = {node["id"]: node["label"] for node in diagram["nodes"]}
    rows = []
    for edge in diagram["edges"]:
        box_width = 170
        left = _label_lines(labels[edge["source"]], 10.5, box_width - 16)
        right = _label_lines(labels[edge["target"]], 10.5, box_width - 16)
        box_height = max(58, 20 + 13 * max(len(left), len(right)))
        start, end = box_width + 5, width - box_width - 5
        edge_lines = _label_lines(edge.get("label", ""), 9, end - start - 4)
        arrow_y = 8 + box_height / 2
        drawing = Drawing(width, max(box_height + 20, arrow_y + 24 + len(edge_lines) * 11))
        for x, lines in [(0, left), (width - box_width, right)]:
            drawing.add(Rect(x, 8, box_width, box_height, rx=5, ry=5,
                             fillColor=colors.HexColor("#f5f2ec"), strokeColor=ACCENT))
            for index, line in enumerate(lines):
                drawing.add(String(x + box_width / 2, arrow_y + (len(lines) - 1) * 6.5 - 4 - index * 13, line,
                                   fontName="LearningSans", fontSize=10.5,
                                   textAnchor="middle", fillColor=INK))
        drawing.add(Line(start, arrow_y, end - 7, arrow_y, strokeColor=ACCENT, strokeWidth=1.4))
        drawing.add(Polygon([end, arrow_y, end - 8, arrow_y + 4, end - 8, arrow_y - 4], fillColor=ACCENT, strokeColor=ACCENT))
        for index, label in enumerate(edge_lines):
            drawing.add(String(width / 2, arrow_y + 12 + (len(edge_lines) - 1 - index) * 11, label, fontName="LearningSans",
                               fontSize=9, textAnchor="middle", fillColor=ACCENT))
        rows.append(drawing)
    return rows


def render_notebook(notebook: dict) -> bytes:
    _fonts()
    body = ParagraphStyle("LearningBody", fontName="LearningSans", fontSize=11.5, leading=17,
                          textColor=INK, spaceAfter=10, splitLongWords=True)
    h1 = ParagraphStyle("LearningH1", parent=body, fontSize=24, leading=30, textColor=ACCENT, spaceAfter=18)
    h2 = ParagraphStyle("LearningH2", parent=body, fontSize=18, leading=24, spaceBefore=16,
                        spaceAfter=12, keepWithNext=True)
    h3 = ParagraphStyle("LearningH3", parent=body, fontSize=14, leading=20, textColor=ACCENT,
                        spaceBefore=14, keepWithNext=True)
    small = ParagraphStyle("LearningSmall", parent=body, fontSize=9, leading=14)
    code_style = ParagraphStyle("LearningCode", fontName="Courier", fontSize=9.5,
                               leading=14, backColor=colors.HexColor("#f0eef3"), borderPadding=9,
                               spaceBefore=8, spaceAfter=14)
    story = []

    def prose(value, style=body):
        for part in re.split(r"\n\s*\n|\n", str(value)):
            if part.strip():
                story.append(Paragraph(escape(part.strip()), style))

    def bullet_list(values):
        for value in values:
            prose("• " + value)

    story.extend([Spacer(1, 75), Paragraph("PLACEAI / LEARNING HUB", small), Spacer(1, 18),
                  Paragraph(escape(notebook["title"]), h1)])
    request, plan = notebook["input"], notebook["plan"]
    prose(f"{request['level'].capitalize()} · {request['chapters']} chapters · Detailed study notes")
    prose(plan["introduction"])
    prose("AI-authored learning material based on web research. Check the cited official documentation "
          "for version-specific details. Code examples are illustrative and have not been executed by PlaceAI.", small)
    story.append(PageBreak())
    story.append(Paragraph("Contents", h1))
    for index, chapter in enumerate(plan["chapters"], 1):
        story.append(Paragraph(f'<link href="#chapter-{index}" color="#59416f">'
                               f'{index:02d}. {escape(chapter["title"])}</link>', body))
        for subtopic in chapter["subtopics"]:
            prose("    " + subtopic, small)
    story.append(Paragraph("Before you begin", h2))
    bullet_list(plan["prerequisites"])
    for index, chapter in enumerate(notebook["chapters"], 1):
        story.append(PageBreak())
        story.append(Paragraph(f'<a name="chapter-{index}"/>{index:02d}. {escape(chapter["title"])}', h1))
        prose(chapter["overview"])
        for subtopic in chapter["subtopics"]:
            story.append(Paragraph(escape(subtopic["title"]), h2))
            prose(subtopic["explanation"])
            refs = " ".join(f'<link href="#source-{n}" color="#59416f">[{n}]</link>' for n in subtopic["source_ids"])
            story.append(Paragraph("Sources: " + refs, small))
        for example in chapter["examples"]:
            story.append(Paragraph("Worked example: " + escape(example["title"]), h2))
            if example["code"]:
                prose(example["language"], small)
                lines = []
                for line in example["code"].expandtabs(4).splitlines():
                    # Never clip long SQL queries or collapse original line breaks.
                    lines.extend(wrap(line, width=77, replace_whitespace=False, drop_whitespace=False,
                                      subsequent_indent="    ") or [""])
                story.append(Preformatted("\n".join(lines), code_style))
            prose(example["explanation"])
            story.append(Paragraph("Expected result", h3))
            prose(example["expected_result"])
        for diagram in chapter["diagrams"]:
            story.append(Paragraph("Diagram: " + escape(diagram["title"]), h2))
            story.extend(diagram_rows(diagram))
            prose(diagram["explanation"])
        story.append(Paragraph("Common mistakes", h2))
        bullet_list(chapter["common_mistakes"])
        story.append(Paragraph("Practice and solutions", h2))
        for number, exercise in enumerate(chapter["exercises"], 1):
            prose(f"{number}. {exercise['question']}")
            story.append(Paragraph("Solution and reasoning", h3))
            prose(exercise["solution"])
        story.append(Paragraph("Key takeaways", h2))
        bullet_list(chapter["key_takeaways"])
    story.append(PageBreak())
    story.append(Paragraph("Sources and further reading", h1))
    prose("References retrieved during this notebook's research. Chapter citations link to the source numbers below.")
    for index, source in enumerate(notebook["sources"], 1):
        url = escape(source["url"], quote=True)
        story.append(Paragraph(f'<a name="source-{index}"/>[{index}] {escape(source["title"])}', h3))
        story.append(Paragraph(f'<link href="{url}" color="#59416f">{url}</link>', small))
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(595.28, 841.89), leftMargin=52, rightMargin=52,
                            topMargin=54, bottomMargin=52, title=notebook["title"], author="PlaceAI Learning Hub")

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("LearningSans", 8)
        canvas.setFillColor(ACCENT)
        canvas.drawString(52, 27, "PlaceAI | Learning Hub")
        canvas.drawRightString(543, 27, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
