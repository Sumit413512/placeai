"""Isolated application submission burst. Never connects to production or AI.

Run: python -m scripts.benchmark_assessment_queue --students 2000 --concurrency 32
SQLite results measure application behavior; use staging for capacity certification.
"""
import argparse
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, get_db
from app.dependencies import require_student
from app.models import AssessmentJob, Job, MockInterview, Organization, RecruiterProfile, StudentProfile, User, UserRole
from app.routers.mock_interview_v2 import router, student_ai_guard


def run(students, concurrency):
    with tempfile.TemporaryDirectory(prefix="placeai-queue-burst-") as directory:
        engine = create_engine(f"sqlite:///{Path(directory) / 'isolated.db'}",
                               connect_args={"check_same_thread": False, "timeout": 60},
                               pool_size=concurrency, max_overflow=0)

        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine, tables=[model.__table__ for model in (
            Organization, User, StudentProfile, RecruiterProfile, Job, MockInterview, AssessmentJob)])
        question = [{"question_id": 1, "question": "Choose SQL", "answer_type": "mcq",
                     "section": "technical", "correct_answer": "SQL"}]
        with Session(engine) as db:
            db.add(User(id="recruiter", email="recruiter@benchmark.invalid", username="recruiter",
                        hashed_password="not-a-credential", role=UserRole.recruiter))
            db.flush()
            db.add(RecruiterProfile(id="recruiter-profile", user_id="recruiter"))
            db.flush()
            db.add(Job(id="job", recruiter_id="recruiter-profile", title="Isolated benchmark", description="Synthetic"))
            db.flush()
            db.add_all([User(id=f"student-{n}", email=f"student-{n}@benchmark.invalid", username=f"student-{n}",
                             hashed_password="not-a-credential", role=UserRole.student) for n in range(students)])
            db.flush()
            db.add_all([StudentProfile(id=f"profile-{n}", user_id=f"student-{n}", full_name="Synthetic student") for n in range(students)])
            db.flush()
            db.add_all([MockInterview(id=f"exam-{n}", student_id=f"profile-{n}", job_id="job",
                                     questions_json=json.dumps(question), answers_json="[]") for n in range(students)])
            db.commit()
        app = FastAPI()
        app.include_router(router)

        def session():
            with Session(engine) as db:
                yield db

        def student(request: Request, db=Depends(get_db)):
            return db.get(User, request.headers["x-synthetic-student"])

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[require_student] = student
        app.dependency_overrides[student_ai_guard] = lambda: None
        settings = get_settings()
        previous = settings.assessment_queue_enabled
        settings.assessment_queue_enabled = True
        try:
            with TestClient(app) as client:
                def submit(number):
                    began = time.perf_counter()
                    response = client.post("/mock-interview/evaluate", headers={"x-synthetic-student": f"student-{number}"},
                                           json={"interview_id": f"exam-{number}", "answers": [{"question_id": 1, "answer": "SQL"}]})
                    return response.status_code, (time.perf_counter() - began) * 1000

                began = time.perf_counter()
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    results = list(pool.map(submit, range(students)))
                elapsed = time.perf_counter() - began
            with Session(engine) as db:
                saved = db.query(AssessmentJob).count()
                finalized = db.query(MockInterview).filter(MockInterview.overall_score.isnot(None)).count()
            latencies = sorted(ms for _, ms in results)
            report = {"backend": "isolated SQLite WAL; not a production capacity claim", "students": students,
                      "concurrency": concurrency, "accepted": sum(status == 202 for status, _ in results),
                      "saved_jobs": saved, "premature_final_scores": finalized,
                      "elapsed_seconds": round(elapsed, 2), "submissions_per_second": round(students / elapsed, 2),
                      "p50_ms": round(latencies[len(latencies) // 2], 2),
                      "p95_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * .95))], 2),
                      "provider_calls": 0}
            print(json.dumps(report, indent=2))
            if saved != students or report["accepted"] != students or finalized:
                raise RuntimeError("Submission burst did not preserve every exam")
            return report
        finally:
            settings.assessment_queue_enabled = previous
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=2000)
    parser.add_argument("--concurrency", type=int, default=32)
    args = parser.parse_args()
    if not 1 <= args.students <= 10000 or not 1 <= args.concurrency <= 128:
        parser.error("Use 1–10000 students and 1–128 concurrent clients")
    run(args.students, args.concurrency)
