"""Derive study progress from owned resources, never client-supplied percentages."""
from __future__ import annotations
import json
import math
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import and_, or_
from app.models import (User, StudentProfile, LearningNotebook, MockInterview,
                        VideoCourse, VideoEnrollment, utcnow)
from app.roadmap_models import CareerRoadmap
from app.study_models import StudyPlan, StudyGoal, NotebookProgress, StudyDaily


def local_day(now, zone='Asia/Kolkata'):
    return now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone)).date()


def user_zone(db, user_id):
    plan = db.query(StudyPlan).filter_by(user_id=user_id).order_by(StudyPlan.created_at).first()
    return plan.timezone if plan else 'Asia/Kolkata'


def lock_owner(db, user):
    db.query(User).filter_by(id=user.id).with_for_update().one()


def notebook(db, identifier, user):
    row = db.query(LearningNotebook).filter_by(id=identifier, user_id=user.id, deleted_at=None).first()
    if not row:
        raise HTTPException(404, 'Notebook not found')
    return row


def sections(book):
    from app.routers.learning_hub import serialize
    if not serialize(book)['ready_to_begin']:
        return []
    return [{'key': f'{i+1}.{j+1}', 'chapter': chapter['title'], 'title': sub['title']}
            for i, chapter in enumerate(json.loads(book.chapters_json))
            for j, sub in enumerate(chapter['subtopics'])]


def reading_data(db, book):
    outline = sections(book)
    records = db.query(NotebookProgress).filter_by(notebook_id=book.id).all()
    by_key = {r.section_key: r for r in records}
    last = max(records, key=lambda r:r.last_read_at) if records else None
    total = len(outline)
    completed = sum(bool(by_key.get(s['key']) and by_key[s['key']].completed) for s in outline)
    return {'notebook_id': book.id, 'sections': [{**s, 'completed': bool(by_key.get(s['key']) and by_key[s['key']].completed)} for s in outline],
            'completed': completed, 'total': total, 'percent': int(100*completed/total) if total else 0,
            'last_section': last.section_key if last else None,
            'basis': 'Sections you mark complete. Last-read position is saved separately.'}


def day_row(db, user_id, now):
    day = local_day(now, user_zone(db, user_id))
    row = db.get(StudyDaily, (user_id, day))
    if row is None:
        row = StudyDaily(user_id=user_id, day=day, notes_seconds=0, video_seconds=0, sections_completed=0)
        db.add(row)
        db.flush()
    return row


def record_video_time(db, user, seconds, now):
    # All study writes lock the owner before resource rows, including concurrent tabs.
    daily = day_row(db, user.id, now)
    elapsed = max(0, (now-daily.last_pulse_at).total_seconds()) if daily.last_pulse_at else 0
    daily.video_seconds += int(min(60, elapsed, max(0, seconds)))
    daily.last_pulse_at = now


def owned_roadmap(db, identifier, user):
    row = db.query(CareerRoadmap).join(StudentProfile, StudentProfile.id == CareerRoadmap.student_id).filter(
        CareerRoadmap.id == identifier, StudentProfile.user_id == user.id).first()
    if not row:
        raise HTTPException(404, 'Roadmap not found')
    return row


def roadmap_milestones(row):
    result = []
    for i, phase in enumerate(row.roadmap.get('phases', [])[:30]):
        for j, value in enumerate(phase.get('outcomes', [])[:20]):
            if isinstance(value, str) and value.strip():
                result.append({'key': f'{i}:{j}', 'title': value[:240], 'phase': str(phase.get('name', ''))[:180]})
    return result


def mock_records(db, user):
    rows = db.query(MockInterview).join(StudentProfile).filter(StudentProfile.user_id == user.id,
        MockInterview.overall_score.is_not(None)).order_by(MockInterview.created_at.desc()).limit(2000).all()
    return [r for r in rows if isinstance(json.loads(r.evaluation_json or '{}'), dict)
            and json.loads(r.evaluation_json or '{}').get('analysis_status', 'complete') == 'complete']


def goal_data(db, goal, user, mocks):
    done, total, minutes, unavailable, resume = goal.manual_completed, goal.target, 30, False, None
    if goal.kind == 'notes':
        book = db.query(LearningNotebook).filter_by(id=goal.resource_id,user_id=user.id,deleted_at=None).first()
        if book:
            progress = reading_data(db, book); done, total = progress['completed'], progress['total'] or goal.target
            resume = {'view':'learning-hub','notebook':book.id,'section':progress['last_section']}
        else: unavailable = True; done = 0
        minutes = 8
    elif goal.kind == 'video':
        from app.routers.learning_video import owner_course, course_data
        try:
            course = owner_course(db, goal.resource_id, user); data = course_data(db, course, user)
            done, total = data['completed_parts'], len(data['lessons']) or goal.target
            minutes = max(3, round(sum(x['duration_seconds'] for x in data['lessons']) / max(total,1) / 60) + 2)
            resume = {'view':'learning-hub','course':course.id}
        except HTTPException: unavailable = True; done = 0
    elif goal.kind == 'mock':
        done, minutes, resume = len(mocks), 45, {'view':'mock-interview'}
    done = max(0,min(done,total))
    return {'id':goal.id,'kind':goal.kind,'resource_id':goal.resource_id,'title':goal.title,'completed':done,
            'target':total,'percent':int(100*done/total) if total else 0,'unavailable':unavailable,'resume':resume,
            'remaining_minutes':(total-done)*minutes,'manual':goal.kind in {'task','milestone'}}


def plan_data(db, plan, user, mocks):
    goals = [goal_data(db,g,user,mocks) for g in db.query(StudyGoal).filter_by(plan_id=plan.id).order_by(StudyGoal.created_at,StudyGoal.id).all()]
    remaining = sum(g['remaining_minutes'] for g in goals)
    days = math.ceil(remaining/plan.daily_minutes)
    today = local_day(utcnow(), plan.timezone)
    return {'id':plan.id,'title':plan.title,'roadmap_id':plan.roadmap_id,'daily_minutes':plan.daily_minutes,
            'target_date':str(plan.target_date) if plan.target_date else None,'timezone':plan.timezone,'paused':plan.paused,
            'goals':goals,'percent':int(sum(g['percent'] for g in goals)/len(goals)) if goals else 0,
            'estimated_days_remaining':days,'estimated_finish':str(today+timedelta(days=days)),
            'pace_notice':'Estimate based on remaining sections, lessons and practice goals; adjust to your pace.',
            'progress_basis':'Average completion across your goals. Reading is self-reported; videos include quizzes.'}


def resource_catalog(db, user):
    from app.routers.learning_hub import serialize
    books = db.query(LearningNotebook).filter_by(user_id=user.id,deleted_at=None).order_by(LearningNotebook.created_at.desc()).limit(50).all()
    courses = db.query(VideoCourse).filter(or_(
        and_(VideoCourse.user_id == user.id, VideoCourse.shared_key.is_(None)),
        and_(VideoCourse.shared_key.is_not(None), db.query(VideoEnrollment).filter(
            VideoEnrollment.user_id == user.id, VideoEnrollment.course_id == VideoCourse.id).exists()))).order_by(VideoCourse.created_at.desc()).limit(30).all()
    roads = db.query(CareerRoadmap).join(StudentProfile).filter(StudentProfile.user_id == user.id).order_by(CareerRoadmap.created_at.desc()).limit(10).all()
    return {'notes':[{'id':b.id,'title':b.title,'sections':len(sections(b))} for b in books if serialize(b)['ready_to_begin']],
            'videos':[{'id':c.id,'title':c.title} for c in courses],
            'roadmaps':[{'id':r.id,'title':r.title,'estimated_days':r.roadmap.get('estimated_days'),
                         'weekly_hours':r.roadmap.get('weekly_hours'),'milestones':roadmap_milestones(r)} for r in roads]}
