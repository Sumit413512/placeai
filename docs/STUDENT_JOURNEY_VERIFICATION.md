# Student journey and technical practice release — 24 October 2026

Historical release note: the separate technical practice feature below was retired and replaced by Zensar inside Mock Interview Coach. See ZENSAR_PROCTORED_PRACTICE.md. Navigation and tracker fixes remain.

## Problems and resulting behaviour

Workspace navigation used replaceState for each screen, so browser Back could jump to an older standalone mock-interview page. The central navigation path now records distinct workspace entries and restores the selected screen on Back/Forward. Initial sign-in/reload restoration replaces rather than duplicates entries. Slow read responses from abandoned views cannot overwrite the current page.

The interview page previously placed large external proctor libraries ahead of its local interface script. Those libraries now load on demand during the required system check, with bounded download failure and retry. Proctor checks remain mandatory for the full assessment. No scoring weights or recording permissions were relaxed.

Study tracker removes the manual Another reminder control. A returning visit advances the welcome quote and rotates three local illustrations and coordinated paper/rose/plum surfaces. Existing courses, goals and progress are preserved. Graphics require no generation or external API.

## Interview benchmark and scoring

Review used primary product documentation, not claims of matching proprietary algorithms:

- Yoodli: https://support.yoodli.ai/en/articles/9550465-practice-with-yoodli
- Big Interview: https://support.biginterview.com/en/article/practiceai-qxju4/
- Big Interview feedback FAQ: https://support.biginterview.com/en/article/videoai-feedback-faq-k8t2ds/

Relevant patterns are visible feedback, answer transcripts, reviewable attempts and practical timing. PlaceAI already supports recorded answer evidence, transcripts, timestamped review, code execution, objective answer keys and server-managed spoken windows. The interface now explains the existing scoring sources and weights. No claim is made that its practice score predicts hiring, verifies personality or matches a competitor algorithm. Fluency and AI feedback are estimates requiring human review.

## Technical companion

New private technical foundations exam: 16 answer-key questions, four sections, 24 minutes. Topics cover SQL/data, programming/debugging, APIs/security and systems/delivery. Choices are shuffled; the versioned bank can recur on repeat attempts. This is objective foundations practice, not an executable coding or spoken interview replacement.

Answers are autosaved on the server before they are marked saved. The server owns the deadline and answer keys. Starting again resumes an active attempt; request UUIDs make retries idempotent. Owner checks guard reads, saves, submissions and history. Completed reports are immutable and expose answers and explanations only after completion. Late reads finalise saved work; late answer edits are rejected. A row lock serialises concurrent saves/submissions. A separate private table keeps these scores out of academic eligibility, full interview readiness and existing mock interview totals.

No AI calls, paid infrastructure, new provider subscription or browser database grants are required. The additive migration creates a private table with RLS, no anon/authenticated access, and the existing server runtime access pattern. Provision the reviewed SQL with the existing database owner before a restricted-runtime rollout; Alembic migration 0026 then verifies/records the release.

## Verification scope

Server tests cover scoring, no answer-key leak before submission, private ownership, strict input validation, saved work, idempotency and deadline expiry. Browser tests cover the mock-to-workspace-to-video Back/Forward regression, reload persistence, technical exam saving/review, automatic welcome rotation, existing audio/video recording/timers and video playback/quizzes. Broader existing tests walk all role navigation pages at desktop/tablet/mobile sizes and check authentication and private document workflows.

A green test run establishes these checked behaviours, not a guarantee that every external provider, device, permission prompt or production account state has no defects. Real microphone/camera quality depends on the device and browser; automated media verification uses controlled synthetic input. Live deployment and public asset checks are recorded in the release report outside this source document.
