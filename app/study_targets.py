"""Recurring study goals and a single evening recap for each student."""
from __future__ import annotations

import json
import logging
from datetime import time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models import NotificationPreference, User, UserRole, utcnow
from app.services import create_notification
from app.study_models import StudyDaily, StudyTargets
from app.study_service import local_day, lock_owner, mock_records

logger = logging.getLogger(__name__)
METRICS = {
    'minutes': ('min', 'min'),
    'notes': ('note section', 'note sections'),
    'lessons': ('video lesson with quiz', 'video lessons with quizzes'),
    'mocks': ('mock interview', 'mock interviews'),
}


def activity(db, user, first, last, zone, mocks=None):
    values = dict.fromkeys(METRICS, 0)
    rows = db.query(StudyDaily).filter(
        StudyDaily.user_id == user.id, StudyDaily.day.between(first, last)).all()
    values['minutes'] = sum(row.notes_seconds + row.video_seconds for row in rows) // 60
    values['notes'] = sum(row.sections_completed for row in rows)
    values['lessons'] = sum(row.lessons_completed for row in rows)
    if mocks is None:
        mocks = mock_records(db, user, since=first, zone=zone)
    values['mocks'] = sum(first <= local_day(row.completed_at or row.created_at, zone) <= last for row in mocks)
    return values


def window_progress(targets, actual):
    return {key: {'done': actual[key], 'target': targets.get(key, 0),
                  'left': max(0, targets.get(key, 0) - actual[key])}
            for key in METRICS}


def progress(db, user, today, zone, mocks):
    row = db.get(StudyTargets, user.id)
    monday = today - timedelta(days=today.weekday())
    return {
        'reminders': bool(row and row.reminders),
        'day': today.isoformat(),
        'week_start': monday.isoformat(),
        'week_end': (monday + timedelta(days=6)).isoformat(),
        'daily': window_progress(json.loads(row.daily_json) if row else {},
                                 activity(db, user, today, today, zone, mocks)),
        'weekly': window_progress(json.loads(row.weekly_json) if row else {},
                                  activity(db, user, monday, today, zone, mocks)),
    }


def describe(values):
    return ', '.join(f'{count} {METRICS[key][count != 1]}'
                     for key, count in values.items() if count)


def create_due_digest(db, user, now):
    row = db.get(StudyTargets, user.id)
    if not row or not row.reminders:
        return False

    local = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(row.timezone))
    day = local.date() if local.time() >= time(20) else local.date() - timedelta(days=1)
    if row.reminder_start_day is None or day < row.reminder_start_day:
        return False
    if row.last_digest_day and day <= row.last_digest_day:
        return False

    lock_owner(db, user)
    db.refresh(row)
    if not row.reminders or not row.reminder_start_day or day < row.reminder_start_day:
        return False
    if row.last_digest_day and day <= row.last_digest_day:
        return False
    preference = db.query(NotificationPreference).filter_by(user_id=user.id).first()
    if preference and not preference.in_app:
        return False

    monday = day - timedelta(days=day.weekday())
    week = activity(db, user, monday, day, row.timezone)
    daily = week if monday == day else activity(db, user, day, day, row.timezone)
    completed = describe(daily)
    message = [f'Completed {completed}.' if completed else 'No study activity recorded for this day.']
    for period, actual, targets in (
        ('Daily', daily, json.loads(row.daily_json)),
        ('Weekly', week, json.loads(row.weekly_json)),
    ):
        if any(targets.values()):
            remaining = describe({key: entry['left'] for key, entry in window_progress(targets, actual).items()})
            message.append(f'{period} targets still need {remaining}.' if remaining else f'{period} targets met.')
    create_notification(db, user.id, f'Study recap · {day.strftime("%d %b")}', ' '.join(message),
                        category='learning', link='study-tracker')
    row.last_digest_day = day
    db.commit()
    return True


def run_recaps(stop):
    """Render generates recaps while it is awake. The inbox catches up on return."""
    while not stop.is_set():
        try:
            cursor = ''
            now = utcnow()
            while not stop.is_set():
                with SessionLocal() as db:
                    batch = db.query(User.id).join(StudyTargets).filter(
                        StudyTargets.reminders.is_(True), User.is_active.is_(True), User.role == UserRole.student,
                        User.id > cursor).order_by(User.id).limit(200).all()
                if not batch:
                    break
                for (user_id,) in batch:
                    if stop.is_set():
                        return
                    with SessionLocal() as db:
                        user = db.get(User, user_id)
                        if user and user.is_active and user.role == UserRole.student:
                            create_due_digest(db, user, now)
                cursor = batch[-1][0]
        except Exception:
            logger.exception('Study recap worker failed')
        stop.wait(300)
