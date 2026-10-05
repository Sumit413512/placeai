"""Run as a persistent background worker: python -m app.assessment_worker.

No background threads are started in the web/serverless application.
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
    try:
        with Session() as db:
            db.info["assessment_lease"] = (interview_id, token)
            user = db.get(User, user_id)
            if not user or not user.is_active or user.role != UserRole.student:
                raise RuntimeError("Assessment owner unavailable")
            result = evaluate_inline(MockInterviewEvaluationV2.model_validate_json(payload), user, db)
            complete = result.get("analysis_status") == "complete"
    except Exception as error:
        LOGGER.warning("Assessment deferred error_type=%s", type(error).__name__)
    finally:
        done.set()
        heartbeat.join(timeout=5)
        with Session() as db:
            assessment_queue.finish(db, interview_id, token, complete)


def main():
    settings = get_settings()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Multi-worker admission requires PostgreSQL")
    if not settings.assessment_queue_enabled:
        raise RuntimeError("Enable the queue only after migrations and worker configuration")
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: STOP.set())
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = set()
        while not STOP.is_set():
            active = {future for future in active if not future.done()}
            if len(active) < 2:
                try:
                    with Session() as db:
                        item = assessment_queue.claim(db, settings.assessment_queue_concurrency,
                                                      settings.assessment_queue_starts_per_minute)
                    if item:
                        active.add(pool.submit(process, item))
                        continue
                except Exception as error:
                    LOGGER.warning("Assessment queue unavailable error_type=%s", type(error).__name__)
            STOP.wait(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
