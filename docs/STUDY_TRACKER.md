# Study tracker and notebook recovery

Study tracker links private student goals to an owned notebook, enrolled video course,
completed mock interviews, a saved roadmap outcome, or a personal task. It makes no
AI/provider calls and does not alter assessment scores, eligibility or placement readiness.

## Progress semantics

- Notes have stable chapter/subtopic keys (for example 1.6). Visible reading position
  is saved separately from explicit section completion. PDF users can mark all sections
  through a chosen checkpoint. Completion is self-reported, not proof of comprehension.
- A focused reader provides a section outline, resume, previous/next controls, adjustable
  type, diagrams, examples, chapter practice and revision. Hidden/background/idle reading
  does not earn active time. Repeated saves and concurrent tabs cannot double-count a
  section or award more time than elapsed wall-clock time.
- Video goals read the viewer's existing playback coverage and quiz completion. Shared
  media never shares a student's progress. Mock goals count only actual complete scored
  assessments, including existing completed sessions; clients cannot submit the count.
- Overall progress is the average of goal percentages. Percentages cannot round to 100
  before all units are complete. Scheduling estimates use remaining units and the daily
  target, not an AI prediction. Plans can be paused and their pace/target adjusted.
- Daily time covers active web reading and supported playback. Offline reading is not
  timed. Interview activity is grouped by session start date. No retrospective study
  time is invented for older records. Study streaks reflect recorded activity only.

## Deletion and safety

Delete moves a notebook to Deleted notes and clears any processing lease. Its owner can
restore the content and reading history. Hidden notebooks cannot be read, downloaded,
retried or edited through normal resource APIs. Recovery does not resurrect deleted work.
This is recoverable deletion, not permanent erasure; the interface states this explicitly.

Every operation authenticates the student and checks resource ownership/enrollment on
server. New tables use RLS with no Data API privileges for anon/authenticated. The existing
private runtime role is the only application policy; no service key is in frontend assets.
Writes serialize on the user before resource rows. Plan admission and goals are bounded;
notes use compact daily aggregates rather than an unbounded heartbeat event stream.

Deploy the additive schema before the application release. Alembic verifies private table
permissions/policies on the Render runtime. No paid service or additional worker is needed.

## Verification

Tests cover private access, real notes/PDF progress, completed assessment counts, shared
video viewer isolation, request idempotency, wall-clock caps, goal derivation, recoverable
deletion, worker lease fencing, migration data preservation, four-role sign-in handoff,
and browser -> API -> isolated database -> UI -> refresh at 320/390/768/1440 widths.
PostgreSQL CI checks concurrent check-ins against the actual database engine. Synthetic
fixture text is test content and is never published to students.
