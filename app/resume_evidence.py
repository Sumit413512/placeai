"""Versioned, local resume coaching. Quotes are observations, never skill verification."""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from pypdf import PdfReader
from app.study_models import NotebookProgress

VERSION = 'placeai-evidence-1'
PRESETS = {
    'Data engineer': ['Python', 'SQL', 'ETL', 'Data modelling', 'Git', 'Cloud'],
    'Software engineer': ['Programming', 'Data structures', 'SQL', 'Git', 'Testing', 'APIs'],
    'Frontend developer': ['JavaScript', 'HTML', 'CSS', 'React', 'Git', 'Accessibility'],
    'Data analyst': ['SQL', 'Excel', 'Python', 'Data visualisation', 'Statistics'],
}
ALIASES = {
    'cloud': ['aws', 'azure', 'google cloud', 'gcp'],
    'programming': ['python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'golang'],
    'apis': ['api', 'apis', 'rest', 'restful'],
    'testing': ['pytest', 'junit', 'unit tests', 'integration tests', 'testing'],
    'etl': ['etl', 'elt', 'extract transform load'],
    'data modelling': ['data modelling', 'data modeling', 'star schema', 'dimensional model'],
    'data visualisation': ['data visualization', 'data visualisation', 'power bi', 'tableau'],
    'data structures': ['data structures', 'algorithms'],
    'accessibility': ['accessibility', 'wcag', 'aria'],
    'javascript': ['javascript', 'js'], 'postgresql': ['postgresql', 'postgres'],
    'react': ['react', 'reactjs', 'react.js'],
}
ACTION = re.compile(r'\b(built|developed|implemented|designed|created|deployed|automated|tested|analysed|analyzed|optimised|optimized|reduced|improved|maintained|integrated|led)\b', re.I)
NEGATIVE = re.compile(r'\b(no|not|never|without|lack|lacking|unfamiliar|learning|beginner|basic|introductory|exposure)\b', re.I)
DENIAL = re.compile(r'\b(no|not|never|without|lack|lacking|unfamiliar)\b', re.I)


def normalize(value):
    return ' '.join(str(value or '').split())


def target_config(profile):
    try:
        rows = json.loads(profile.role_requirements_json or '[]')
    except (ValueError, TypeError):
        rows = []
    return {'role': normalize(profile.target_role), 'requirements': rows}


def target_hash(profile):
    return hashlib.sha256(json.dumps(target_config(profile), sort_keys=True).encode()).hexdigest()


def contains(text, term):
    return bool(re.search(r'(?<![\w])' + re.escape(term) + r'(?![\w])', text, re.I))


def extract_lines(raw):
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 30:
            raise ValueError()
        rows = []
        total = 0
        for page_number, page in enumerate(reader.pages, 1):
            for line_number, value in enumerate((page.extract_text() or '').splitlines(), 1):
                text = normalize(value)
                if not text:
                    continue
                total += len(text)
                if total > 50_000:
                    raise HTTPException(422, 'Resume text exceeds the safe analysis limit. Upload a shorter resume.')
                rows.append({'page': page_number, 'line': line_number, 'quote': text})
        if sum(len(x['quote']) for x in rows) < 50:
            raise HTTPException(422, 'No readable resume text. Upload a text-based PDF; scanned PDFs need OCR first.')
        return rows, len(reader.pages)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, 'Could not safely read this PDF. Use an unencrypted, text-based PDF of 30 pages or fewer.') from exc


def requirement_result(requirement, lines, profile_skills):
    term = requirement['label']
    alternatives = [term, *ALIASES.get(term.lower(), [])]
    matches = [row for row in lines if any(contains(row['quote'], t) for t in alternatives)]
    affirmative = [row for row in matches if not DENIAL.search(row['quote'])]
    # Context, not a skills list alone, is required for full documentary credit.
    strong = [row for row in matches if ACTION.search(row['quote']) and not NEGATIVE.search(row['quote'])]
    status = 'documented' if strong else ('partial' if affirmative else 'not_found')
    quotes = (strong or affirmative or matches)[:2]
    claimed = any(any(contains(skill, t) for t in alternatives) for skill in profile_skills)
    explanation = {
        'documented': 'A resume line describes using this requirement. This remains an unverified student claim.',
        'partial': 'Mentioned, but applied experience is unclear or qualified. Add a truthful project example.',
        'not_found': 'No matching line was found. This means absent from the document, not that you lack the skill.',
    }[status]
    if matches and not affirmative:
        explanation = 'The matching line is negative or explicitly qualified as lacking experience. It earns no credit; review the quote.'
    return {**requirement, 'status': status, 'weight': 2 if requirement['priority'] == 'required' else 1,
            'credit': 1 if strong else (0.5 if affirmative else 0), 'evidence': quotes,
            'profile_claim': claimed, 'explanation': explanation,
            'practice_question': f'Describe a project where you used {term}. Explain your contribution, a trade-off and how you checked the result.' if strong else f'How would you practise {term} in a small project, and what evidence would demonstrate the result?'}


def analyze(raw, profile):
    lines, pages = extract_lines(raw)
    text = '\n'.join(row['quote'] for row in lines)
    applied = [x for x in lines if ACTION.search(x['quote']) and not NEGATIVE.search(x['quote'])]
    measurable = [x for x in applied if re.search(r'\b\d+(?:\.\d+)?\s*(?:%|users?|requests?|seconds?|minutes?|hours?|records?|tests?|ms\b)', x['quote'], re.I)]
    checks = []

    def check(key, label, weight, hits, fix):
        checks.append({'key': key, 'label': label, 'weight': weight, 'earned': weight if hits else 0,
                       'status': 'observed' if hits else 'review', 'evidence': hits[:2], 'suggestion': fix})

    def find(pattern):
        return [row for row in lines if re.search(pattern, row['quote'], re.I)]

    check('readable', 'Readable PDF text', 15, lines[:1], 'Keep a text-based PDF with a clear reading order.')
    check('education', 'Education section', 15, find(r'\b(education|bachelor|master|b\.tech|b\.e\.|diploma|university)\b'), 'Add your course, institution and graduation year. Do not invent credentials.')
    check('skills', 'Skills section', 10, find(r'\b(skills|technologies|technical proficiency)\b'), 'Group relevant skills under a clear Skills heading.')
    check('experience', 'Projects or experience section', 15, find(r'\b(projects?|experience|internship)\b'), 'Include at least one project or relevant experience section.')
    check('contribution', 'Specific contributions', 20, applied, 'Use action + what you built + your contribution. Example template: Built [feature] using [technology] to solve [problem].')
    check('outcomes', 'Measurable outcomes', 15, measurable, 'Where available, add a truthful scale, test result or outcome. Never invent numbers.')
    check('links', 'Portfolio or code reference', 10, find(r'(github\.com/|gitlab\.com/|portfolio|https?://)'), 'Add a relevant code or portfolio link. Links are detected, not independently verified.')
    config = target_config(profile)
    requirements = [requirement_result(row, lines, profile.skills) for row in config['requirements']] if config['role'] else []
    total = sum(x['weight'] for x in requirements)
    role_score = int(sum(x['weight'] * x['credit'] for x in requirements) / total * 100) if total else None
    words = len(text.split())
    adjustments = []
    cap = 100
    if words < 120:
        cap = 40
        adjustments.append(f'Only {words} readable words: document score capped at 40 until sufficient resume detail is present.')
    elif words < 250:
        cap = 70
        adjustments.append(f'{words} readable words: document score capped at 70; check that education, contributions and project context are complete.')
    if words > 1800 or pages > 4:
        cap = min(cap, 75)
        adjustments.append('More than 1,800 words or 4 pages: this student-resume rubric caps the score at 75 and recommends a focused application version.')
    improvements = [x['suggestion'] for x in checks if x['status'] == 'review']
    if any(len(x['quote'].split()) > 40 for x in applied):
        improvements.append('Break contribution statements longer than 40 words into concise action, context and result bullets.')
    improvements.extend(adjustments)
    return {'version': VERSION, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'content_hash': hashlib.sha256(raw).hexdigest(), 'target_hash': target_hash(profile),
            'method': 'Local evidence rubric; no external AI upload', 'pages': pages, 'word_count': words,
            'resume_score': min(cap, sum(x['earned'] for x in checks)), 'score_adjustments': adjustments,
            'checks': checks, 'target_role': config['role'],
            'role_score': role_score, 'requirements': requirements, 'project_examples': applied[:5],
            'improvements': improvements,
            'limitations': ['Documentary coverage is not a verified skill, hiring recommendation or universal ATS score.',
                            'Local matching can miss synonyms or split PDF lines. Review the quoted text and checklist.',
                            'Names, photos, age, gender, contact details and institution prestige do not earn points.',
                            'Visual layout, grammar and link ownership require human review.']}


def saved_review(profile):
    if not profile.resume:
        return None
    try:
        result = json.loads(profile.resume.evidence_review_json or 'null')
    except (TypeError, ValueError):
        return None
    return result if isinstance(result, dict) and result.get('version') == VERSION else None


def alignment(profile):
    result = saved_review(profile)
    current = bool(result and result.get('target_hash') == target_hash(profile))
    return {'score': result.get('role_score') if current else None, 'current': current,
            'target_role': profile.target_role, 'requirements': result.get('requirements', []) if current else [],
            'message': 'Quoted resume coverage against your selected checklist; not a verified competency score.' if current else 'Choose a target role and checklist, then run the evidence review on your current resume.'}


def preparation_context(profile, user, db):
    """Private activity context; completion must not be relabelled as competence."""
    from app.models import LearningNotebook, VideoCourse, VideoLesson, VideoProgress, VideoViewerProgress
    from app.study_service import mock_records
    notes = db.query(NotebookProgress).join(LearningNotebook, NotebookProgress.notebook_id == LearningNotebook.id).filter(
        LearningNotebook.user_id == user.id, LearningNotebook.state == 'ready', NotebookProgress.completed.is_(True)).count()
    private_video = db.query(VideoProgress.lesson_id).join(VideoLesson, VideoProgress.lesson_id == VideoLesson.id).join(
        VideoCourse, VideoLesson.course_id == VideoCourse.id).filter(VideoCourse.user_id == user.id,
        VideoProgress.video_completed.is_(True), VideoProgress.practice_completed.is_(True)).all()
    shared_video = db.query(VideoViewerProgress.lesson_id).filter(VideoViewerProgress.user_id == user.id,
        VideoViewerProgress.video_completed.is_(True), VideoViewerProgress.practice_completed.is_(True)).all()
    return {'course': profile.degree, 'semester': profile.current_semester, 'profile_skills': profile.skills,
            'notes_sections': notes, 'video_units': len({x[0] for x in [*private_video, *shared_video]}),
            'completed_assessments': len(mock_records(db, user)),
            'note': 'Profile skills are self-reported. Learning completion records show activity, not verified mastery or role-specific eligibility. They do not add resume or alignment points.'}
