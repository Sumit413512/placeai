# Processing recovery and dedicated workers

Platform Admin → Processing recovery lists failed assessment jobs, notebooks, and
courses with failed, missing or unreviewed lessons. Request repair retains submitted
answers, passed media and progress IDs. Each request is audited, rate limited and
subject to a 30-minute duplicate cooldown. Course repair admission reserves against
the existing storage budget and a global 40-part repair allowance per rolling day.
Missing legacy lessons are admitted by the existing bounded scheduler.

Do not replace failed media with guessed scores or bypass the three publication
checks. A repeated content rejection invalidates its unpublished script/media so
the next attempt can author a correction rather than replay the known defect.
Provider-capacity failures retain private media and narration checkpoints.

## Dedicated worker rollout (additional paid compute needs owner approval)

Use the existing PlaceAI repository and release commit, in the existing Render
workspace/region. No Redis, new database or student-data copy is required.

Assessment worker:

    python scripts/run_processing_worker.py --kind assessments

Learning worker:

    python scripts/run_processing_worker.py --kind learning

Build assessments with `pip install -r requirements.txt`; build learning with
`pip install -r requirements.txt -r requirements-video.txt && python scripts/prepare_learning_voice.py --verify`.
Use production settings and the same authorized database/provider/transactional
email configuration through private Render secrets. Never commit secret values.
Keep the existing lease/concurrency/storage limits during rollout.

Verify each worker actually claims and completes a synthetic or owner-authorized
queued task and resumes an interrupted lease. Only then turn off the corresponding
in-process loop on the web service. Retain the existing service until convergence
and recovery are verified. Dedicated workers have no public HTTP route; use queue
heartbeats/logs and overdue-job alerts to assess processing readiness.

MFA enrollment requires each administrator's authenticator and recovery-code
handling. Do not enroll someone else's device or turn on a hard access gate before
the owner's recovery path has been verified.
