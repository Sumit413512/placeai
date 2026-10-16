# PlaceAI Video Learning

Learning Hub now contains Detailed notes and Video learning. A topic and starting
level create a researched 4–12 lesson path. Students prepare each lesson on demand.
The course and approved scripts survive deploys; an interrupted worker lease can
be reclaimed. Generation stops after three unsuccessful or interrupted attempts.

Each lesson is an actual H.264/AAC MP4 made from precisely rendered slides, code
and diagrams with AI-generated narration. References and an independent automated
content review precede speech generation. Examples are illustrative, never executed.
English automatically timed captions and a descriptive transcript accompany playback.
Caption cues are estimated within measured scene audio boundaries; they are not word-aligned.

Progress is private and durable. Resume position and unique watched intervals are
saved separately from server-graded practice. Seeking does not award watched time;
90% coverage marks a video viewed. Three correct answers mark practice complete.
These indicators are learning aids, not proctored attendance or mastery certificates.

## Operations and limits

- Render's existing learning-worker setting also starts a separate video worker.
  Video generation has its own admission lock, independent from assessment grading.
- Existing server-side Gemini/OpenAI keys are reused. Gemini speech uses the REST
  Interactions API so the existing SDK does not need upgrading. Speech model defaults
  are `gemini-3.8-flash-lite-tts` and fallback `tts-1`; optional overrides are
  `LEARNING_TTS_GEMINI_MODEL` and `LEARNING_TTS_OPENAI_MODEL`.
- The speech provider must support the configured model and have available quota.
  Unavailable providers never produce a fabricated success or silent lesson.
- Per student: three new paths and eight new lessons per rolling day.
  Platform-wide: thirty paths and forty lessons per rolling day.
- Lessons are capped at eight minutes and 3 MiB. Private media storage is capped
  at 150 MiB with reservations for queued work, protecting the current small database.
  Increase capacity through a deliberate storage migration before wider rollout.
- Lesson media is authenticated, fetched into bounded in-memory browser blobs and
  released when switching lessons/leaving the page. Tokens never appear in URLs.
- New tables have RLS and deny public, anon and authenticated Data API roles.
  Only the existing trusted backend runtime/service roles can access them;
  application routes enforce the signed-in student's ownership on every operation.
- No paid plans, payment integration, new user permissions or public storage buckets.

## Verification

`test_learning_video.py` covers ownership, unauthenticated requests, idempotency,
budgets, grading, seek protection, lease recovery, provider failure, content bounds,
caption escaping and actual MP4 decoding. The browser test exercises creation,
native video loading, captions, resume, speed, practice, mobile widths and cleanup.
The PostgreSQL test checks concurrent admission and exhausted-lease handling.
