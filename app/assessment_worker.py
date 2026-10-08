"""Run as a persistent background worker: python -m app.assessment_worker.

An opt-in worker can also run in the existing persistent Render web process.
Serverless processes never start this worker.
"""
import logging
import signal
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread

from sqlalchemy.orm import sessionmaker

from app import assessment_queue
from app.config import get_settings
from app.database import engine
from app.models import User, UserRole

LOGGER = logging.getLogger(__name__)
Session = sessionmaker(bind=engine, expire_on_commit=False)
STOP = Event()
PROVIDER_ERROR_CODES = frozenset({
    "VIDEO_PROVIDER_BUSY",
    "VIDEO_PROVIDER_CAPACITY",
    "VIDEO_PROVIDER_ACCESS",
    "VIDEO_PROVIDER_MODEL",
    "VIDEO_PROVIDER_UNAVAILABLE",
    "AI_PROVIDER_CAPACITY",
    "AI_PROVIDER_UNAVAILABLE",
})


def process(item):
    from app.routers.mock_interview_v2 import MockInterviewEvaluationV2, evaluate_inline

    interview_id, user_id, payload, token = item
    done = Event()

    def renew():
        while not done.wait(30):
            try:
                with Session() as db:
                    if not assessment_queue.heartbeat(db, interview_id, token):
                        return
            except Exception:
                LOGGER.warning("Assessment heartbeat unavailable")

    heartbeat = Thread(target=renew, daemon=True)
    heartbeat.start()
    complete = False
    error_code = None
    try:
        with Session() as db:
            db.info["assessment_lease"] = (interview_id, token)
            user = db.get(User, user_id)
            if not user or not user.is_active or user.role != UserRole.student:
                raise RuntimeError("Assessment owner unavailable")
            result = evaluate_inline(MockInterviewEvaluationV2.model_validate_json(payload), user, db)
            complete = result.get("analysis_status") == "complete"
    except Exception as error:
        detail = getattr(error, "detail", None)
        if isinstance(detail, dict) and detail.get("code") in PROVIDER_ERROR_CODES:
            error_code = detail["code"]
        LOGGER.warning(
            "Assessment deferred error_type=%s error_code=%s",
            type(error).__name__,
            error_code or "unclassified",
        )
    finally:
        done.set()
        heartbeat.join(timeout=5)
        with Session() as db:
            assessment_queue.finish(db, interview_id, token, complete, error_code=error_code)


def run(stop, max_workers=1):
    settings = get_settings()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Multi-worker admission requires PostgreSQL")
    if not settings.assessment_queue_enabled:
        raise RuntimeError("Enable the queue only after migrations and worker configuration")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        active = set()
        while not stop.is_set():
            active = {future for future in active if not future.done()}
            if len(active) < max_workers:
                try:
                    with Session() as db:
                        item = assessment_queue.claim(db, settings.assessment_queue_concurrency,
                                                      settings.assessment_queue_starts_per_minute)
                    if item:
                        active.add(pool.submit(process, item))
                        continue
                except Exception as error:
                    LOGGER.warning("Assessment queue unavailable error_type=%s", type(error).__name__)
            stop.wait(2)


def main():
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: STOP.set())
    run(STOP)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
