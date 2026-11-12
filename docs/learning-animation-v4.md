# PlaceAI Visual Learning V4 — Animated Concept Teaching Standard

**Scope:** newly requested shared video-learning courses. The approved PlaceAI PNG
must remain unchanged, readable and located at the **top-left on every frame**.
Do not change existing student progress, regenerate approved legacy media, or
replace the supplied PNG with an approximation.

## Reference study and original creative direction

The supplied reference screenshots demonstrate a useful *teaching technique*:
first pose a question, then animate the relevant data structures or values,
emphasise the traversed element, correct a likely misunderstanding, and only
then show the result. Their creator's imagery, watermark, mascot, layouts,
voice and proprietary assets are **not** licensed to PlaceAI and are not copied.

The PlaceAI visual identity is a distinct premium ivory/mint/soft-green board
with dark-ink text and controlled burgundy contrast. Source-grounded movements
are meaningful rather than merely decorative. Diagrams use large labels and
one highlighted action at a time; the final takeaway is one sentence.

## Rendering architecture

1. Gemini research supplies citations, lesson objective, accurate worked
   examples and prerequisite order. Learner uploads and third-party text
   remain untrusted and never become instructions.
2. The lesson author produces a validated `VideoStoryboard` on at least three
   concept scenes for new V4 material, using one of:
   `array`, `linked_list`, `flow`, `timeline`, `bar_chart`,
   `compare`, `code_trace`. No arbitrary user-created Python/JS is executed.
3. Pydantic validates labels, focus, chart numbers, readability and visual
   bounds; the local Pillow renderer preflights multiple animation phases
   before the system spends narration quota.
4. Narration is produced using the configured TTS provider; on-screen
   English labels are distinct from spoken natural Hindi in Devanagari
   interleaved with correct English technical terms. The speech engine must
   pronounce each language naturally. Text prompts alone cannot guarantee
   that an offline English-only synthesizer will produce good Hindi.
5. An existing bounded PyAV/H.264/AAC encoder generates actual MP4 frames
   using each scene's **measured** narration duration, with source media kept
   private, the exact PlaceAI logo visible and the legacy language footer
   removed. In-scene visual timing is approximate, **not word-aligned**.
6. PyAV decodes the output to check the tracks, frame clock, non-silence,
   brand area, file size and boundaries. An independent provider review must
   listen to the actual audio and check the animation's meaning, language
   quality and direction. Human platform-admin review remains mandatory
   before learners see the course.

## Semantics of the supported animations

- **Array:** square cells with persistent index numbers. `action=direct`
  must jump directly to the correct index; `action=scan` may inspect each
  cell in order. Never show a loop when claiming direct O(1) access.
- **Linked list:** nodes connect through arrows that represent pointers and
  terminate at NULL. Arrows never indicate numerical addition.
- **Flow / timeline:** sequential steps appear in source-supported order.
- **Bar chart:** only evidence-backed numeric comparisons or unmistakably
  illustrative examples; values must match the visual heights.
- **Compare:** distinguish concrete concepts by visual treatment rather than
  adding filler words.
- **Code trace:** point to actual concise source lines, never imply that
  illustrated example code was executed.

## Audio quality and future production upgrades

Gemini-TTS supports the Hindi and Indian English language styles and
voice-control instructions needed here. The existing configured provider and
vendor quotas remain operator-controlled: **do not silently turn on a paid
fallback or upload learner private data to another TTS company.**

For high-scale production, evaluate a dedicated animation rendering worker
based on Remotion (React frame-timed motion) and Manim Community (rigorous
mathematical transformations). Add forced-alignment/word-level timings only
after validating provider accuracy, licensing and usage cost. These
optional tools are **not** dependencies of the first V4 release: adding heavy
browser/LaTeX stacks to the existing free-tier web worker would reduce
availability without controlled load testing.

## Release acceptance / no-regression checklist

- [ ] Every new course has at least three valid animated concept scenes.
- [ ] Index/pointer/arrows/chart numbers are mathematically and technically correct.
- [ ] No user-provided HTML, executable code or unsafe Python is run.
- [ ] Brand PNG checksum and first and last frame brand pixels remain identical.
- [ ] No copied reference watermark, character or language-instruction footer.
- [ ] MP4 is downloadable only by authorized viewers or platform staff.
- [ ] Every saved video passes decoded media/timing and editorial reviews.
- [ ] Native Hindi and technical English are auditioned on a real sample from
      the configured production speech provider. **Screenshot-only inspection
      cannot satisfy this voice acceptance check.**
- [ ] Existing courses and learner watch history remain intact; V4 uses a
      separate shared cache generation to prevent pretending V3 videos are V4.
- [ ] New H.264 output remains within the existing storage/CPU quotas.
- [ ] CI, browser playback, security and release smoke are green.

## Product limitation

No generative system can guarantee error-free or unforgettable teaching.
Source-grounding, deterministic diagram semantics, automated media review,
human editorial decisions and operational monitoring substantially reduce
the risk, and keep unverified material from being shown to customers.
