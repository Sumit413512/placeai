# Separate spoken answers and delayed reports

New standardized assessments always use question-scoped recordings. Every question is read in full before recording. Spoken questions use an audio-only recorder; each HR question has a separate camera-and-audio recorder. System narration is not recorded. The server binds each immutable recording to its issued question, checks consent, limits duration and bytes, and permits playback only for the student and their authorized institution admin. Legacy continuous HR recordings remain readable.

Each validated question analysis is persisted separately. A later quota/provider failure preserves the submitted media and reuses completed analyses on recovery. All section scores remain hidden until every required question has an evaluation; absent or unusable evidence receives an explicit insufficient-evidence result, never invented speech.

## Enablement gates

1. Apply Alembic `20261005_0017` using the migration owner. The existing Render runtime role receives only the approved private table grants; public/client access stays denied with RLS enabled.
2. Confirm the actual production provider project's data-handling terms, available model quota and an evidence-grounded synthetic-media evaluation. Google unpaid API terms exclude personal information. Do not route student recordings through unpaid Gemini capacity. GPT-5.6 Sol has no free API tier and cannot directly accept audio/video. ChatGPT plan integrations require eligible app/user authorization and cannot turn one owner's subscription into unrestricted backend capacity.
3. Run a human-reviewed grading benchmark, including silence, irrelevant speech, regional accents, clear correct answers, partial answers and provider recovery. No accuracy certification is claimed from mocked tests.
4. Delayed reporting uses `ENABLE_ASSESSMENT_QUEUE=true` on both production runtimes. The Render web service runs one worker with `ASSESSMENT_WORKER_IN_PROCESS=true`; Vercel never starts a worker. Hourly fallback convergence wakes the free Render service, so the student-facing contract is a complete report within 24 hours rather than an instant score.
5. Continuously verify starts, separate uploads, expiry/retention, partial-analysis recovery, all-section report completion, historical report retrieval and authenticated playback in production. Do not convert an assessment already in progress.

Quota rejections use a safe capacity error and stop rapid browser retries. An enabled queue defers such failures for 15 minutes, with bounded attempts and saved submissions; it is not a substitute for usable quota.

Sources: [Gemini terms](https://ai.google.dev/gemini-api/terms), [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [GPT-5.6 Sol modalities and free tier](https://developers.openai.com/api/docs/models/gpt-5.6-sol), [eligible ChatGPT plan integration](https://developers.openai.com/siwc/quickstart).
