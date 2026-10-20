import io
import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from app import learning_ai
from app.learning_content import LearningChapter
from app.learning_format import inline, blocks
from app.learning_notes_prompt import NOTES_AUTHORING_STANDARD
from app.learning_pdf import render_notebook
from test_learning_hub import chapter_data, plan_data, preferences


def advanced_chapter():
    chapter = chapter_data()
    chapter["subtopics"][0]["explanation"] = "**Predicate** means a condition that selects rows.\n- Keep matching rows.\n1. Read the table.\n2. Evaluate the predicate.\n" + chapter["subtopics"][0]["explanation"]
    chapter["comparisons"] = [{"title": "WHERE and HAVING", "columns": ["Clause", "Filters", "When"],
                              "rows": [["WHERE", "Individual rows", "Before grouping"], ["HAVING", "Groups", "After grouping"]]}]
    chapter["formulas"] = [{"title": "Matching row percentage", "expression": "percentage = (matching_rows / total_rows) * 100",
                            "variables": [{"term": "matching_rows", "meaning": "Number of rows satisfying the predicate."},
                                          {"term": "total_rows", "meaning": "Number of source rows, greater than zero."}],
                            "worked_example": "Two of four rows match the predicate. Divide two by four to get 0.5. Multiply by 100 to obtain fifty percent of the source rows.",
                            "interpretation": "Half the source rows satisfy this filter; an empty source needs separate handling."}]
    chapter["key_terms"] = [{"term": "Predicate", "meaning": "A condition evaluated to decide whether a row qualifies."}]
    chapter["exam_focus"] = ["Explain the distinction between filtering rows and filtering groups."]
    chapter["interview_questions"] = [{"question": "When should a query use WHERE instead of HAVING?",
                                       "solution": "Use WHERE to filter individual rows before grouping. HAVING filters groups after aggregation. Both can be used together when their predicates have different purposes."}]
    chapter["next_topics"] = ["GROUP BY and aggregate functions"]
    return chapter


def test_old_notebooks_remain_valid_and_supplements_are_bounded():
    assert LearningChapter.model_validate(chapter_data()).comparisons == []
    assert LearningChapter.model_validate(advanced_chapter()).formulas[0].variables
    raw = advanced_chapter(); raw["comparisons"][0]["rows"][0].pop()
    with pytest.raises(ValidationError): LearningChapter.model_validate(raw)
    raw = advanced_chapter(); raw["formulas"][0]["variables"] = []
    with pytest.raises(ValidationError): LearningChapter.model_validate(raw)
    raw = chapter_data(); raw["diagrams"] = []
    assert LearningChapter.model_validate(raw).diagrams == []


def test_emphasis_and_lists_cannot_introduce_active_markup():
    result = inline('**Predicate** <img src=x onerror=alert(1)> & <script>bad()</script>')
    assert '<b>Predicate</b>' in result
    assert '<img' not in result and '<script>' not in result
    assert '&lt;img' in result and '&amp;' in result
    assert list(blocks('Intro\n- One\n1. First\n2. Second')) == [('', 'Intro'), ('• ', 'One'), ('1. ', 'First'), ('2. ', 'Second')]


def test_advanced_notes_are_preserved_in_pdf_and_html_stays_literal():
    chapter = advanced_chapter()
    chapter['overview'] += ' **Important term** <script>window.bad=1</script>'
    book = {"title": "SQL notes rendering verification", "input": preferences(), "plan": plan_data(),
            "chapters": [chapter], "sources": [{"title": "PostgreSQL", "url": "https://www.postgresql.org/docs/current/"}]}
    book["plan"]["chapters"] = book["plan"]["chapters"][:1]
    payload = render_notebook(book)
    reader = PdfReader(io.BytesIO(payload))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for value in ('WHERE and HAVING', 'Matching row percentage', 'matching_rows', 'Worked calculation',
                  'Interpretation', 'Key terms', 'Interview insight', 'Important for exams', 'Quick revision', 'What to learn next'):
        assert value in text
    assert '**Important term**' not in text
    assert '<script>window.bad=1</script>' in text
    assert len(reader.pages) > 3


def test_review_gate_rejects_errors_in_supplemental_material(monkeypatch):
    captured = []
    def review(task, schema, **kwargs):
        captured.append(task)
        return {"approved": False, "issues": ["Worked formula contradicts its interpretation"]}, "test:review"
    monkeypatch.setattr(learning_ai, 'generate_json', review)
    with pytest.raises(ValueError): learning_ai.review_chapter(advanced_chapter(), 'Verified evidence', preferences())
    assert 'formula variables/calculations/interpretation' in captured[0]
    assert NOTES_AUTHORING_STANDARD in captured[0]
