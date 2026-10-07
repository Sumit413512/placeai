from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, f"{label}: expected 1 match, found {count}"
    return text.replace(old, new, 1)


def replace_block(text, start, end, replacement, label):
    a = text.find(start)
    assert a >= 0, f"{label}: start marker missing"
    b = text.find(end, a)
    assert b >= 0, f"{label}: end marker missing"
    return text[:a] + replacement + text[b:]


# Server recording contract.
p = Path("app/answer_recording.py")
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    'POST_HR_VOICE_SECTIONS = frozenset({"role", "situational"})\n',
    'ASSESSMENT_AUDIO_SECTIONS = frozenset({"resume", "role", "situational"})\n'
    'POST_HR_VOICE_SECTIONS = ASSESSMENT_AUDIO_SECTIONS  # compatibility alias\n',
    "audio sections constant",
)
s = replace_block(
    s,
    "def materialize_post_hr_modes(questions):\n",
    '\n\n@event.listens_for(MockInterview, "before_insert")',
    '''def materialize_post_hr_modes(questions):
    """Persist required private-audio modes for a standardized full assessment.

    Practice rounds are deliberately excluded. Resume/Project Defence, Role/JD and
    Situational answers are spoken; Behavioural/HR keeps its continuous video flow.
    Legacy in-flight items that already have an explicit video mode remain unchanged.
    """
    if not is_full_assessment_questions(questions):
        return False
    changed = False
    for question in questions:
        if not isinstance(question, dict):
            continue
        section = str(question.get("section", "")).strip().lower()
        answer_type = str(question.get("answer_type", "text")).strip().lower()
        if section not in ASSESSMENT_AUDIO_SECTIONS or answer_type not in {"text", "audio"}:
            continue
        if question.get("response_mode") not in {"audio", "video"}:
            question["response_mode"] = "audio"
            changed = True
        if question.get("response_mode") == "audio" and question.get("answer_type") != "audio":
            question["answer_type"] = "audio"
            changed = True
        if question.get("narration_enabled") is not True:
            question["narration_enabled"] = True
            changed = True
    return changed
''',
    "materialize spoken modes",
)
s = replace_once(
    s,
    '    """Store mandatory post-HR audio metadata before a new assessment reaches the DB."""\n',
    '    """Store mandatory assessment-audio metadata before a new assessment reaches the DB."""\n',
    "insert hook docstring",
)
s = replace_block(
    s,
    "def response_mode(question):\n",
    "\n\ndef _persist_inferred_mode",
    '''def response_mode(question):
    """Return the effective spoken-answer mode without changing legacy HR behavior.

    Standardized Resume/Project, Role/JD and Situational responses are private audio.
    Behavioural/HR keeps its existing continuous camera recording unless an older
    server-issued question already carries an explicit response mode.
    """
    explicit = question.get("response_mode")
    if explicit in {"audio", "video"}:
        return explicit
    section = str(question.get("section", "")).strip().lower()
    answer_type = str(question.get("answer_type", "text")).strip().lower()
    if section in ASSESSMENT_AUDIO_SECTIONS and answer_type in {"text", "audio"}:
        return "audio"
    return None
''',
    "effective response mode",
)
s = replace_block(
    s,
    "def _persist_inferred_mode(db, interview, question_id, mode):\n",
    "\n\ndef owned(",
    '''def _persist_inferred_mode(db, interview, question_id, mode):
    """Persist inferred assessment-audio metadata without releasing the row lock."""
    questions = json.loads(interview.questions_json or "[]")
    changed = False
    for item in questions:
        if item.get("question_id") != question_id:
            continue
        if item.get("response_mode") not in {"audio", "video"}:
            item["response_mode"] = mode
            item["narration_enabled"] = True
            changed = True
        if mode == "audio" and item.get("answer_type") != "audio":
            item["answer_type"] = "audio"
            changed = True
        break
    if changed:
        interview.questions_json = json.dumps(questions)
        db.flush()
''',
    "persist inferred audio",
)
helper = '''def _answer_time_seconds(question):
    """Use the server-issued spoken-answer window, bounded by the recording policy."""
    try:
        requested = int(question.get("answer_time_seconds") or hr_video.QUESTION_SECONDS)
    except (TypeError, ValueError):
        requested = hr_video.QUESTION_SECONDS
    return max(45, min(requested, hr_video.QUESTION_SECONDS))


'''
s = replace_once(s, "def begin(db, user, interview_id, question_id, mime_type, consent):\n", helper + "def begin(db, user, interview_id, question_id, mime_type, consent):\n", "answer time helper")
s = replace_once(
    s,
    "                          deadline_at=min(now + timedelta(seconds=hr_video.QUESTION_SECONDS),\n                                          root.exam_started_at + timedelta(minutes=hr_video.EXAM_MINUTES)),\n",
    "                          deadline_at=min(now + timedelta(seconds=_answer_time_seconds(question)),\n                                          root.exam_started_at + timedelta(minutes=hr_video.EXAM_MINUTES)),\n",
    "question deadline",
)
p.write_text(s, encoding="utf-8")


# Standardized assessment generation and issuance contract.
p = Path("app/routers/mock_interview_v2.py")
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '    ("situational", "Situational & Decision", 2),\n)\n',
    '    ("situational", "Situational & Decision", 2),\n)\n'
    'OBJECTIVE_ASSESSMENT_SECTIONS = frozenset({"quantitative", "logical", "communication", "technical", "programming"})\n'
    'AUDIO_ASSESSMENT_SECTIONS = frozenset({"resume", "role", "situational"})\n'
    'SPOKEN_ANSWER_SECONDS = {"resume": 120, "role": 90, "situational": 120}\n',
    "assessment constants",
)
s = replace_once(
    s,
    "Resume, behavioral, role and situational items should normally be applied-response questions.",
    "Resume, behavioral, role and situational items MUST be open-ended spoken-response questions. Do not create typed descriptive or essay answers for the standardized assessment.",
    "generation instruction",
)
s = replace_once(
    s,
    '\"answer_type\":\"mcq|text\",\"options\":[\"A\",\"B\",\"C\",\"D\"],\"correct_answer\":\"exact option text or empty for text\"',
    '\"answer_type\":\"mcq|audio|video\",\"options\":[\"A\",\"B\",\"C\",\"D\"],\"correct_answer\":\"exact option text or empty for spoken\"',
    "generation schema",
)
contract = '''def _apply_standard_assessment_response_contract(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make the 50-item response pattern server-authoritative and textarea-free."""
    if len(questions) != FULL_MOCK_QUESTION_COUNT:
        raise HTTPException(502, "Standardized assessment generation is incomplete")
    counts = {key: 0 for key, _, _ in ASSESSMENT_BLUEPRINT}
    for item in questions:
        section = str(item.get("section", "")).strip().lower()
        if section not in counts:
            raise HTTPException(502, "Standardized assessment contains an unsupported section")
        counts[section] += 1
        if section in OBJECTIVE_ASSESSMENT_SECTIONS:
            options = [str(value).strip() for value in (item.get("options") or [])]
            correct = _resolve_correct_option(options, str(item.get("correct_answer", ""))) if len(options) == 4 else ""
            if len(options) != 4 or len({value.casefold() for value in options}) != 4 or not correct:
                raise HTTPException(502, "Standardized objective question is malformed")
            item["answer_type"] = "mcq"
            item["options"] = options
            item["correct_answer"] = correct
            item.pop("response_mode", None)
            item["narration_enabled"] = False
        elif section == "coding":
            item["answer_type"] = "code"
            item["options"] = []
            item["correct_answer"] = ""
            item.pop("response_mode", None)
            item["narration_enabled"] = False
        elif section == "behavioral":
            item["answer_type"] = "video"
            item["options"] = []
            item["correct_answer"] = ""
            item.pop("response_mode", None)
            item["narration_enabled"] = False
        elif section in AUDIO_ASSESSMENT_SECTIONS:
            item["answer_type"] = "audio"
            item["response_mode"] = "audio"
            item["narration_enabled"] = True
            item["answer_time_seconds"] = SPOKEN_ANSWER_SECONDS[section]
            item["options"] = []
            item["correct_answer"] = ""
        else:
            raise HTTPException(502, "Standardized assessment response mode is unsupported")
    expected = {key: count for key, _, count in ASSESSMENT_BLUEPRINT}
    if counts != expected:
        raise HTTPException(502, "Standardized assessment blueprint is incomplete")
    if any(str(item.get("answer_type", "")).lower() == "text" for item in questions):
        raise HTTPException(502, "Descriptive typed answers are not allowed in the standardized assessment")
    return questions


'''
s = replace_once(s, "def _difficulty_for(index: int, total: int, requested: str) -> str:\n", contract + "def _difficulty_for(index: int, total: int, requested: str) -> str:\n", "standard response contract")
old_fallback = '''            chosen.append({
                "question": question[:2000],
                "section": section,
                "category": section,
                "difficulty": _difficulty_for(index + 1, max(missing, 1), difficulty),
                "answer_type": "text",
                "options": [],
                "correct_answer": "",
            })
'''
new_fallback = '''            chosen.append({
                "question": question[:2000],
                "section": section,
                "category": section,
                "difficulty": _difficulty_for(index + 1, max(missing, 1), difficulty),
                "answer_type": "video" if section == "behavioral" else "audio",
                "options": [],
                "correct_answer": "",
            })
'''
s = replace_once(s, old_fallback, new_fallback, "fallback response types")
old_ai = '''                answer_type = "mcq" if count == FULL_MOCK_QUESTION_COUNT and len(options) == 4 and resolved_correct else "text"
                correct_answer = resolved_correct if answer_type == "mcq" else ""
                if answer_type == "text":
                    options = []
'''
new_ai = '''                if count == FULL_MOCK_QUESTION_COUNT:
                    if objective_section:
                        answer_type = "mcq"
                    elif section == "behavioral":
                        answer_type = "video"
                    elif section in AUDIO_ASSESSMENT_SECTIONS:
                        answer_type = "audio"
                    else:
                        continue
                else:
                    answer_type = "text"
                correct_answer = resolved_correct if answer_type == "mcq" else ""
                if answer_type != "mcq":
                    options = []
'''
s = replace_once(s, old_ai, new_ai, "AI response types")
old_order = '''    ordered = (
        _order_full_assessment_items(accepted[:count])
        if count == FULL_MOCK_QUESTION_COUNT
        else accepted[:count]
    )
    questions = [
'''
new_order = '''    ordered = (
        _order_full_assessment_items(accepted[:count])
        if count == FULL_MOCK_QUESTION_COUNT
        else accepted[:count]
    )
    if count == FULL_MOCK_QUESTION_COUNT:
        ordered = _apply_standard_assessment_response_contract(ordered)
    questions = [
'''
s = replace_once(s, old_order, new_order, "generation contract application")
old_start = '''    if body.mode == "assessment":
        for question in questions:
            question["narration_enabled"] = get_settings().question_recordings_enabled
            if question.get("section") == "behavioral":
                question["answer_type"] = "video"
            if get_settings().question_recordings_enabled and question.get("answer_type") in {"text", "video"}:
                question["response_mode"] = "video" if question["answer_type"] == "video" else "audio"
'''
new_start = '''    if body.mode == "assessment":
        _apply_standard_assessment_response_contract(questions)
'''
s = replace_once(s, old_start, new_start, "start response contract")
p.write_text(s, encoding="utf-8")


# Queue documentation follows the broader spoken contract.
p = Path("app/assessment_queue.py")
s = p.read_text(encoding="utf-8")
s = s.replace(
    "Older/in-flight assessments may have Role/JD and Situational questions stored as\n    text because their audio response mode was historically inferred by the browser.",
    "Older/in-flight assessments may have Resume/Project, Role/JD and Situational questions stored\n    as text because their audio response mode was historically inferred by the browser.",
)
s = s.replace(
    "response_mode() recognizes legacy Role/Situational records even before the",
    "response_mode() recognizes legacy standardized spoken records even before the",
)
p.write_text(s, encoding="utf-8")


# Frontend: no descriptive textarea in standardized assessment.
for path in (Path("app/static/mock-interview.js"), Path("public/static/mock-interview.js")):
    s = path.read_text(encoding="utf-8")
    s = replace_once(s, "{key:'resume', label:'Resume & Project Defence', count:4, minutes:10, kind:'text'},", "{key:'resume', label:'Resume & Project Defence', count:4, minutes:10, kind:'audio'},", f"{path} resume blueprint")
    s = replace_once(s, "{key:'role', label:'Role / JD / Company', count:2, minutes:5, kind:'text'},", "{key:'role', label:'Role / JD / Company', count:2, minutes:5, kind:'audio'},", f"{path} role blueprint")
    s = replace_once(s, "{key:'situational', label:'Situational & Decision', count:2, minutes:5, kind:'text'}", "{key:'situational', label:'Situational & Decision', count:2, minutes:5, kind:'audio'}", f"{path} situational blueprint")
    s = replace_once(s, "item.kind === 'video' ? 'Recorded spoken answers' : 'Applied response'", "item.kind === 'video' ? 'Recorded HR video answers' : item.kind === 'audio' ? 'Private spoken answers' : 'Unsupported response'", f"{path} blueprint copy")
    old_demo = "        questions.push({question_id:id++,section:section.key,category:section.label,difficulty:i < Math.ceil(section.count*.4)?'Foundation':i < Math.ceil(section.count*.8)?'Intermediate':'Advanced',question:templates[section.key] || `Explain a role-relevant approach for ${skill}.`,answer_type:'text'});"
    new_demo = "        const spokenAudio=['resume','role','situational'].includes(section.key);\n        const answerTime=section.key==='resume'?120:section.key==='role'?90:120;\n        questions.push({question_id:id++,section:section.key,category:section.label,difficulty:i < Math.ceil(section.count*.4)?'Foundation':i < Math.ceil(section.count*.8)?'Intermediate':'Advanced',question:templates[section.key] || `Explain a role-relevant approach for ${skill}.`,answer_type:section.key==='behavioral'?'video':'audio',...(spokenAudio?{response_mode:'audio',narration_enabled:true,answer_time_seconds:answerTime}:{})});"
    s = replace_once(s, old_demo, new_demo, f"{path} preview response types")
    s = replace_once(s, "  function isAttemptedAnswer(answer) {\n    return Boolean(answer && answer.answer && !String(answer.answer).startsWith('['));\n  }", "  function isAttemptedAnswer(answer) {\n    const value=String(answer?.answer||'');\n    return Boolean(value && !value.startsWith('[No response submitted'));\n  }", f"{path} spoken attempted state")
    old_textarea = '''    $('#next-question').disabled=false;
    $('#save-question').disabled=false;
    area.innerHTML='<label class="answer-field">Your response<textarea id="current-answer" class="secure-textarea" maxlength="5000" autocomplete="off" spellcheck="true" placeholder="Write a concise, evidence-based response."></textarea></label>';
    if(existing?.answer) $('#current-answer').value=existing.answer;
'''
    new_textarea = '''    area.innerHTML='<div class="answer-load-error"><strong>Unsupported response mode</strong><span>This assessment item did not load with an approved MCQ, coding or spoken-answer mode. The assessment is paused to protect scoring integrity.</span></div>';
    $('#next-question').disabled=true;
    $('#save-question').disabled=true;
    logIntegrity('response_mode_invalid','Assessment item attempted to render an unsupported descriptive response mode.','system',null);
'''
    s = replace_once(s, old_textarea, new_textarea, f"{path} textarea removal")
    old_else = '''    } else {
      answer=($('#current-answer')?.value || '').trim();
      if(!answer) { toast('Enter your response before continuing.','error'); return false; }
    }
'''
    new_else = '''    } else {
      toast('This question has an unsupported response mode. Submission is paused to protect scoring integrity.','error');
      return false;
    }
'''
    s = replace_once(s, old_else, new_else, f"{path} descriptive submission removal")
    old_guidance = '''    $('#question-guidance').textContent=q.answer_type==='mcq'
      ? 'Select one option. Use Save answer to keep it on the current question, or Save & Next to lock it and move forward.'
      : q.answer_type==='code'
        ? 'Technical coding question: write a complete program, use Run Code for sample tests, then Submit Code for sample + hidden tests before Save & Next.'
        : 'Respond using clear reasoning and evidence. After submission this question is permanently closed.';
'''
    new_guidance = '''    $('#question-guidance').textContent=q.response_mode==='audio'
      ? 'Listen to the question, then answer aloud. Your private microphone recording is submitted when you continue.'
      : q.answer_type==='video'
        ? 'Answer aloud using the secure HR camera and microphone recording.'
        : q.answer_type==='mcq'
          ? 'Select one option. Use Save answer to keep it on the current question, or Save & Next to lock it and move forward.'
          : q.answer_type==='code'
            ? 'Technical coding question: write a complete program, use Run Code for sample tests, then Submit Code for sample + hidden tests before Save & Next.'
            : 'Unsupported response mode. This item cannot be submitted.';
'''
    s = replace_once(s, old_guidance, new_guidance, f"{path} response guidance")
    old_spoken = "    $('#answer-area').innerHTML='<div class=\"answer-field\"><strong>'+(q.response_mode==='video'?'HR camera and voice answer':'Spoken answer')+'</strong><p>Listen to the question, then answer aloud. This question has its own private recording and up to 2 minutes 30 seconds of answer time.</p><p id=\"spoken-answer-status\" role=\"status\">Reading question…</p><button id=\"start-spoken-answer\" type=\"button\" class=\"button secondary hidden\">Start answer</button>'+(q.response_mode==='video'?'<video id=\"hr-answer-preview\" autoplay playsinline muted aria-label=\"Your live HR camera preview\"></video>':'')+'</div>';"
    new_spoken = "    const answerSeconds=Math.max(45,Math.min(150,Number(q.answer_time_seconds)||150));\n    const answerWindow=answerSeconds%60===0?(answerSeconds/60)+' minute'+(answerSeconds===60?'':'s'):Math.floor(answerSeconds/60)+' min '+(answerSeconds%60)+' sec';\n    $('#answer-area').innerHTML='<div class=\"answer-field\"><strong>'+(q.response_mode==='video'?'HR camera and voice answer':'Spoken answer')+'</strong><p>Listen to the question, then answer aloud. This question has its own private recording with up to '+answerWindow+' of answer time.</p><p id=\"spoken-answer-status\" role=\"status\">Reading question…</p><button id=\"start-spoken-answer\" type=\"button\" class=\"button secondary hidden\">Start answer</button>'+(q.response_mode==='video'?'<video id=\"hr-answer-preview\" autoplay playsinline muted aria-label=\"Your live HR camera preview\"></video>':'')+'</div>';"
    s = replace_once(s, old_spoken, new_spoken, f"{path} spoken duration")
    path.write_text(s, encoding="utf-8")

assert Path("app/static/mock-interview.js").read_bytes() == Path("public/static/mock-interview.js").read_bytes(), "mock interview static mirrors diverged"


# Compatibility layer upgrades in-flight standardized sessions too.
for path in (Path("app/static/assessment-audio-enhancements.js"), Path("public/static/assessment-audio-enhancements.js")):
    s = path.read_text(encoding="utf-8")
    s = replace_once(s, "const POST_HR_VOICE_SECTIONS = new Set(['role', 'situational']);", "const ASSESSMENT_AUDIO_SECTIONS = new Set(['resume', 'role', 'situational']);", f"{path} audio set")
    s = replace_once(s, "const SPOKEN_BLUEPRINT_LABELS = new Set(['Role / JD / Company', 'Situational & Decision']);", "const SPOKEN_BLUEPRINT_LABELS = new Set(['Resume & Project Defence', 'Role / JD / Company', 'Situational & Decision']);", f"{path} labels")
    s = replace_once(s, "const COMPLETE_GRADING_METHOD_LABEL = 'Answer key + sandbox execution + written, spoken and HR video analysis';", "const COMPLETE_GRADING_METHOD_LABEL = 'Answer key + sandbox execution + spoken and HR video analysis';", f"{path} grading label")
    old_decorate = '''      // Keep Resume & Project Defence as text and preserve the current continuous
      // Behavioural/HR video experience. Only the two post-HR response sections
      // become private audio answers while the broad recording rollout is disabled.
      if (POST_HR_VOICE_SECTIONS.has(section) && answerType === 'text' && !next.response_mode) {
        next.response_mode = 'audio';
      }
'''
    new_decorate = '''      // Standardized open-ended non-HR sections are private audio answers.
      // Behavioural/HR keeps its existing continuous video experience.
      if (ASSESSMENT_AUDIO_SECTIONS.has(section)) {
        next.answer_type = 'audio';
        next.response_mode = 'audio';
        next.narration_enabled = true;
        if (!next.answer_time_seconds) next.answer_time_seconds = section === 'resume' ? 120 : section === 'role' ? 90 : 120;
        next.options = [];
      }
'''
    s = replace_once(s, old_decorate, new_decorate, f"{path} assessment decorator")
    path.write_text(s, encoding="utf-8")

assert Path("app/static/assessment-audio-enhancements.js").read_bytes() == Path("public/static/assessment-audio-enhancements.js").read_bytes(), "assessment audio mirrors diverged"


# Existing spoken-policy regression tests.
p = Path("tests/test_post_hr_voice_answers.py")
s = p.read_text(encoding="utf-8")
s = s.replace('elif section in {"resume", "role", "situational"}:\n            answer_type = "text"', 'elif section in {"resume", "role", "situational"}:\n            answer_type = "audio"')
s = s.replace('if question["section"] in {"role", "situational"}\n                else "submitted answer"', 'if question["section"] in {"resume", "role", "situational"}\n                else "submitted answer"')
s = s.replace('def test_post_hr_sections_use_audio_without_changing_resume_or_legacy_hr():', 'def test_standardized_open_ended_sections_use_audio_without_changing_legacy_hr():')
s = s.replace('assert answer_recording.response_mode({"section": "resume", "answer_type": "text"}) is None', 'assert answer_recording.response_mode({"section": "resume", "answer_type": "text"}) == "audio"')
s = s.replace('role_and_situational = [\n        item for item in persisted if item["section"] in {"role", "situational"}\n    ]\n    assert len(role_and_situational) == 4\n    assert all(item["response_mode"] == "audio" for item in role_and_situational)\n    assert all(item["narration_enabled"] is True for item in role_and_situational)', 'spoken_audio = [\n        item for item in persisted if item["section"] in {"resume", "role", "situational"}\n    ]\n    assert len(spoken_audio) == 8\n    assert all(item["response_mode"] == "audio" for item in spoken_audio)\n    assert all(item["answer_type"] == "audio" for item in spoken_audio)\n    assert all(item["narration_enabled"] is True for item in spoken_audio)')
s = s.replace('if item["section"] in {"resume", "behavioral"}', 'if item["section"] == "behavioral"')
s = s.replace('if item["section"] in {"role", "situational"}', 'if item["section"] in {"resume", "role", "situational"}')
s = s.replace('assert len(spoken) == 4', 'assert len(spoken) == 8')
s = s.replace("assert \"new Set(['role', 'situational'])\" in app_js", "assert \"new Set(['resume', 'role', 'situational'])\" in app_js")
s = s.replace('Answer key + sandbox execution + written, spoken and HR video analysis', 'Answer key + sandbox execution + spoken and HR video analysis')
p.write_text(s, encoding="utf-8")


# Explicit no-descriptive standardized-assessment regression coverage.
Path("tests/test_no_descriptive_assessment.py").write_text('''from pathlib import Path

from app import answer_recording
from app.routers import mock_interview_v2

ROOT = Path(__file__).resolve().parents[1]


def _issued_blueprint():
    rows = []
    for section, _, count in mock_interview_v2.ASSESSMENT_BLUEPRINT:
        for index in range(count):
            item = {"question": f"{section} {index}", "section": section, "category": section, "difficulty": "medium"}
            if section in mock_interview_v2.OBJECTIVE_ASSESSMENT_SECTIONS:
                item.update(answer_type="mcq", options=["A", "B", "C", "D"], correct_answer="A")
            elif section == "coding":
                item.update(answer_type="code", options=[], correct_answer="", coding_spec={})
            else:
                item.update(answer_type="text", options=[], correct_answer="")
            rows.append(item)
    return rows


def test_standardized_exam_has_no_descriptive_text_response_mode():
    questions = mock_interview_v2._apply_standard_assessment_response_contract(_issued_blueprint())
    assert len(questions) == 50
    assert sum(q["answer_type"] == "mcq" for q in questions) == 36
    assert sum(q["answer_type"] == "code" for q in questions) == 2
    assert sum(q["answer_type"] == "audio" for q in questions) == 8
    assert sum(q["answer_type"] == "video" for q in questions) == 4
    assert not any(q["answer_type"] == "text" for q in questions)
    for q in questions:
        if q["section"] in {"resume", "role", "situational"}:
            assert q["response_mode"] == "audio"
            assert q["narration_enabled"] is True
            assert q["answer_time_seconds"] == {"resume": 120, "role": 90, "situational": 120}[q["section"]]
        elif q["section"] == "behavioral":
            assert "response_mode" not in q
            assert q["answer_type"] == "video"


def test_legacy_full_assessment_resume_is_upgraded_to_private_audio():
    questions = []
    question_id = 1
    for section, count in answer_recording.FULL_ASSESSMENT_SECTION_COUNTS.items():
        for _ in range(count):
            answer_type = "video" if section == "behavioral" else "code" if section == "coding" else "mcq" if section not in {"resume", "role", "situational"} else "text"
            questions.append({"question_id": question_id, "section": section, "answer_type": answer_type})
            question_id += 1
    assert answer_recording.materialize_post_hr_modes(questions) is True
    spoken = [q for q in questions if q["section"] in {"resume", "role", "situational"}]
    assert len(spoken) == 8
    assert all(q["answer_type"] == "audio" and q["response_mode"] == "audio" for q in spoken)


def test_assessment_frontend_has_no_descriptive_answer_textarea_and_fails_closed():
    app_js = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/mock-interview.js").read_text(encoding="utf-8")
    assert app_js == public_js
    assert "Write a concise, evidence-based response." not in app_js
    assert "Unsupported response mode" in app_js
    assert "response_mode_invalid" in app_js
    assert "kind:'audio'" in app_js
    assert "['resume','role','situational']" in app_js


def test_assessment_audio_compatibility_layer_includes_resume_and_no_written_grading_label():
    app_js = (ROOT / "app/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    assert app_js == public_js
    assert "new Set(['resume', 'role', 'situational'])" in app_js
    assert "Resume & Project Defence" in app_js
    assert "next.answer_type = 'audio'" in app_js
    assert "written, spoken" not in app_js
''', encoding="utf-8")

mock = Path("app/static/mock-interview.js").read_text(encoding="utf-8")
assert "Write a concise, evidence-based response." not in mock
assert "Unsupported response mode" in mock
assert Path("app/static/mock-interview.js").read_bytes() == Path("public/static/mock-interview.js").read_bytes()
assert Path("app/static/assessment-audio-enhancements.js").read_bytes() == Path("public/static/assessment-audio-enhancements.js").read_bytes()
print("NO_DESCRIPTIVE_ASSESSMENT_PATCH_APPLIED")
