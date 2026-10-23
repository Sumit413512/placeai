"""One truthful result status for saved assessment lists and detail views."""
from datetime import datetime, timedelta, timezone
import math


def result_status(interview, job=None, *, submitted=True, now=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    started = getattr(job, 'created_at', None) or interview.created_at or now
    deadline = started + timedelta(hours=24)
    complete = interview.overall_score is not None
    state = 'complete' if complete else 'failed' if job and job.state == 'failed' else (
        'awaiting_submission' if not submitted else 'delayed' if now >= deadline else
        'running' if job and job.state == 'running' else 'queued')
    labels = {'complete': 'Ready', 'failed': 'Needs attention', 'delayed': 'Delayed',
              'running': 'Processing', 'queued': 'Queued', 'awaiting_submission': 'Not submitted'}
    messages = {
        'complete': 'Your complete report is ready.',
        'failed': 'Your answers are saved, but analysis stopped after repeated failures. Retry analysis or contact your institution with the assessment reference.',
        'delayed': 'Your answers are saved. Analysis has exceeded its 24-hour target. Contact your institution with the assessment reference; no final score is available yet.',
        'running': 'Your saved answers are being analyzed. The complete report appears after every required section is checked.',
        'queued': 'Your answers are saved and queued for analysis. The target is within 24 hours of submission; this is not a guaranteed completion time.',
        'awaiting_submission': 'Submit this assessment before a report can be prepared.',
    }
    return {'status': state, 'status_label': labels[state], 'status_message': messages[state],
            'expected_within_hours': max(1, math.ceil((deadline-now).total_seconds()/3600))
            if state in {'queued', 'running'} else None,
            'expected_at': deadline.isoformat()+'Z' if state in {'queued','running','delayed'} else None}
