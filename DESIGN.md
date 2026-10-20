# PlaceAI interface system

PlaceAI connects learning, preparation and campus placement operations. Preserve this identity across roles; do not apply a different company theme to each screen.

## Reference decisions
Reviewed getdesign.md and its public IBM and Linear reference documents. These are independent design analyses, not official company specifications or reusable product code.

- Coursera course pages: catalogue, course overview and syllabus, then a module outline beside the lesson player. Keep quizzes and transcripts attached to their lesson.
- Handshake: career-focused student navigation, actionable opportunities and preparation before secondary administrative detail.
- IBM Carbon data tables: calm surfaces, clear column headers, distinct table toolbars and consistent rows for recruiters and institutions.
- Linear: restrained navigation and clear page hierarchy; retain PlaceAI’s light palette rather than copying its dark identity.

Sources: https://getdesign.md, https://getdesign.md/ibm/design-md, https://getdesign.md/linear.app/design-md, https://www.coursera.org/learn/learning-how-to-learn, https://joinhandshake.com/, https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines

## Tokens and composition
White surfaces on #f6f8fc; primary evergreen #28594f; text #17243b; secondary text #526177. Semantic status colours communicate meaning, always accompanied by text. Use Calibri/Carlito with system fallbacks, normal tracking, regular headings and medium action labels. Spacing: 8, 16, 24, 32 pixels. Controls use 6px corners; surfaces 10px. Keep focus indicators, readable labels and responsive layouts.

Use one primary action per section. Keep supporting details in meaningful disclosures, not duplicated role badges. Tables retain all data and mobile responsive treatment. Learning cards use actual course metadata and saved completion, never invented readiness.

## Functional invariants
Never change authentication, permissions, API contracts, timers, media lifecycle, progress persistence, generation/review gates, exam recording or payments as part of styling. Only fully prepared courses allow learning to begin. Retain keyboard controls, native labels, reduced-motion support and hidden/disabled states. No third-party component runtime or tracking is added.

## October 20 palette refinement
21st.dev was reviewed for component and footer composition. Keep the existing native HTML/CSS rather than introducing a React runtime. Use charcoal hero typography, evergreen actions and coordinated sage, sand, mauve and stone card surfaces. The dark evergreen footer uses warm-white text and a white plaque for the unchanged wordmark. Colours distinguish content groups; status labels retain their semantics.
