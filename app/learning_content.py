"""Bounded, validated teaching content shared by the reader and PDF renderer."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LearningRequest(ContentModel):
    topic: str = Field(min_length=2, max_length=180)
    field: str = Field(default="", max_length=180)
    programming_language: str = Field(default="", max_length=120)
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    goals: str = Field(default="", max_length=2000)
    chapters: Literal[8, 12, 16] = 12
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")


class ChapterPlan(ContentModel):
    title: str = Field(min_length=3, max_length=180)
    subtopics: list[str] = Field(min_length=3, max_length=6)
    objective: str = Field(min_length=20, max_length=600)

    @model_validator(mode="after")
    def specific_subtopics(self):
        if any(len(title) < 3 or len(title) > 180 for title in self.subtopics):
            raise ValueError("Subtopic titles must be concise and specific")
        if len({title.casefold() for title in self.subtopics}) != len(self.subtopics):
            raise ValueError("Subtopic titles must be distinct")
        return self


class LearningPlan(ContentModel):
    title: str = Field(min_length=3, max_length=180)
    introduction: str = Field(min_length=100, max_length=4000)
    prerequisites: list[str] = Field(max_length=12)
    chapters: list[ChapterPlan] = Field(min_length=8, max_length=16)

    @model_validator(mode="after")
    def distinct_chapters(self):
        if len({chapter.title.casefold() for chapter in self.chapters}) != len(self.chapters):
            raise ValueError("Chapter titles must be distinct")
        return self


class Subtopic(ContentModel):
    title: str = Field(min_length=3, max_length=180)
    explanation: str = Field(min_length=500, max_length=16000)
    source_ids: list[int] = Field(min_length=1, max_length=8)


class Example(ContentModel):
    title: str = Field(min_length=3, max_length=180)
    code: str = Field(default="", max_length=8000)
    language: str = Field(default="", max_length=40)
    explanation: str = Field(min_length=200, max_length=8000)
    expected_result: str = Field(min_length=20, max_length=3000)


class DiagramNode(ContentModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,24}$")
    label: str = Field(min_length=1, max_length=70)


class DiagramEdge(ContentModel):
    source: str = Field(max_length=24)
    target: str = Field(max_length=24)
    label: str = Field(default="", max_length=60)


class Diagram(ContentModel):
    title: str = Field(min_length=3, max_length=180)
    nodes: list[DiagramNode] = Field(min_length=2, max_length=8)
    edges: list[DiagramEdge] = Field(min_length=1, max_length=12)
    explanation: str = Field(min_length=150, max_length=5000)

    @model_validator(mode="after")
    def valid_graph(self):
        ids = {node.id for node in self.nodes}
        if len(ids) != len(self.nodes) or any(
            edge.source not in ids or edge.target not in ids or edge.source == edge.target
            for edge in self.edges
        ):
            raise ValueError("Diagram relationships must reference distinct, existing nodes")
        return self


class Exercise(ContentModel):
    question: str = Field(min_length=20, max_length=2000)
    solution: str = Field(min_length=100, max_length=5000)


class LearningChapter(ContentModel):
    title: str = Field(min_length=3, max_length=180)
    overview: str = Field(min_length=100, max_length=2500)
    subtopics: list[Subtopic] = Field(min_length=3, max_length=6)
    examples: list[Example] = Field(min_length=2, max_length=4)
    diagrams: list[Diagram] = Field(min_length=1, max_length=3)
    common_mistakes: list[str] = Field(min_length=2, max_length=8)
    exercises: list[Exercise] = Field(min_length=2, max_length=5)
    key_takeaways: list[str] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def detailed_teaching(self):
        prose = " ".join([self.overview, *(s.explanation for s in self.subtopics),
                          *(e.explanation for e in self.examples),
                          *(d.explanation for d in self.diagrams)])
        if len(re.findall(r"\b\w+\b", prose)) < 800:
            raise ValueError("A chapter needs at least 800 words of actual teaching, excluding code and exercises")
        return self


def validate_chapter(raw: dict, planned: ChapterPlan, source_count: int, programming: bool) -> LearningChapter:
    chapter = LearningChapter.model_validate(raw)
    if len(chapter.subtopics) != len(planned.subtopics):
        raise ValueError("Every planned subtopic must be explained")
    if [s.title.casefold() for s in chapter.subtopics] != [s.casefold() for s in planned.subtopics]:
        raise ValueError("Chapter content must follow its approved subtopic outline")
    if any(i < 1 or i > source_count for s in chapter.subtopics for i in s.source_ids):
        raise ValueError("Citations must refer to retrieved sources")
    if programming and any(not e.code.strip() for e in chapter.examples):
        raise ValueError("Programming examples need code as well as explanations")
    chapter.title = planned.title
    return chapter
