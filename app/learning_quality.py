"""Versioned, deterministic publication checks. Model review is an additional gate."""
import re

from app.learning_content import LearningPlan, validate_chapter

STANDARD_VERSION = 2


def chapter_issues(chapter):
    issues = []
    titles = {s.title for s in chapter.subtopics}
    coverage = {example.subtopic for example in chapter.examples}
    if not titles <= coverage or not coverage <= titles:
        issues.append("Every subtopic needs its own worked example with the exact subtopic title")
    if len({example.title.casefold() for example in chapter.examples}) != len(chapter.examples):
        issues.append("Worked examples need distinct, specific titles")
    for sub in chapter.subtopics:
        lines = [line.strip() for line in sub.explanation.splitlines() if line.strip()]
        if any(len(re.findall(r"\b\w+\b", line)) > 120 for line in lines):
            issues.append(f"Use short paragraphs or list items in {sub.title}")
        if not any(re.match(r"(?:[-•]|\d+[.)])\s+", line) for line in lines):
            issues.append(f"Include meaningful point-wise teaching in {sub.title}")
        if not re.search(r"\*\*[^*\n]{1,100}\*\*", sub.explanation):
            issues.append(f"Emphasize an important defined term in {sub.title}")
        if re.search(r"<\s*(?:script|iframe|img|style)\b|```", sub.explanation, re.I):
            issues.append(f"Use safe prose formatting and structured code fields in {sub.title}")
    for diagram in chapter.diagrams:
        if not diagram.subtopics or not set(diagram.subtopics) <= titles:
            issues.append("Each diagram must identify the exact concepts it explains")
        linked = {edge.source for edge in diagram.edges} | {edge.target for edge in diagram.edges}
        if linked != {node.id for node in diagram.nodes}:
            issues.append("Every diagram node must participate in an explained relationship")
    return issues


def validate_standard(chapter):
    issues = chapter_issues(chapter)
    if issues:
        raise ValueError("Notes standard: " + "; ".join(issues[:12]))
    return chapter


def validate_notebook(plan_data, chapters, source_count, programming, *, version=1):
    plan = LearningPlan.model_validate(plan_data)
    if not chapters or len(chapters) != len(plan.chapters):
        raise ValueError("The complete syllabus must be written before publication")
    for raw, planned in zip(chapters, plan.chapters):
        chapter = validate_chapter(raw, planned, source_count, programming)
        if version >= STANDARD_VERSION:
            validate_standard(chapter)
    return {"version": version, "passed": True, "chapters_checked": len(chapters)}
