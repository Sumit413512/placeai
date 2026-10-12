# Learning Hub

Students open **Career → Learning Hub**, enter their subject, field, programming language/tool,
current level and goals, then choose 8, 12 or 16 detailed chapters. English notes include
subtopic explanations, worked examples and code, expected results, AI-designed diagrams,
common mistakes, solved exercises, takeaways and source references.

## Research and quality

Research uses OpenAI Responses web search, Gemini Google Search grounding, or live retrieval
of approved official documentation and university references. When search-tool quota is
unavailable, AI selects reference candidates and the server fetches and verifies the actual
documents before using their content. Unreachable or insufficient pages are excluded; at
least three live sources are required. Reference candidates alone never count as research.
The retrieval path restricts publishers, public DNS addresses, redirects, content types and
download sizes. Scripts, navigation and footer boilerplate are excluded from evidence. Each chapter performs
its own research, validates its structure and citations, and passes a separate AI content
review. Each chapter requires at least 800 words of teaching prose excluding code and
exercises. These checks improve quality; they do not guarantee every AI explanation is
error-free. Examples are not executed by the platform. Version/dialect caveats and
clickable sources are displayed in both reader and PDF.

Diagrams use validated model-generated nodes and labelled relationships, rendered as
clear vector shapes in the PDF and accessible labelled relationships in the reader.
Raw model HTML, scripts, SVG and arbitrary remote images are never rendered.

## Saved generation

Requests are persisted before generation. The worker prepares an outline and then one
chapter per lease, committing after each successful stage. A student can navigate away,
return to their notebook, and read completed chapters while remaining chapters generate.
The complete PDF becomes available only after every chapter passes validation.

Account-row locking and request identifiers protect against duplicate admission. One
active notebook per student prevents overlapping costly requests, without imposing a
lifetime notebook limit. PostgreSQL advisory locking serializes global admission across
Render instances. Expired leases can be reclaimed; stale writers cannot publish results.
Repeated failures stop after four attempts per stage, preserving completed chapters for
an explicit retry. Admission is ordered by availability time so notebooks share the queue
chapter by chapter. Learning does not consume assessment grading admission slots.

## Runtime and deployment

- Run Alembic through revision `20261010_0020`. Restricted Render roles verify the
  owner-provisioned private tables, grants and policies instead of managing DDL.
- Set a usable `GEMINI_API_KEY` or `OPENAI_API_KEY` on the Render service. A valid key
  with exhausted quota cannot generate notes. Configure the corresponding existing
  `GEMINI_MODEL` or `OPENAI_MODEL` only to an available, supported model.
  `LEARNING_GEMINI_MODEL` overrides the writer model only for this feature, without
  changing existing AI tools. `LEARNING_RESEARCH_MODE=verified_docs` selects verified
  document retrieval when the project has no provider-search-tool quota.
- `LEARNING_WORKER_IN_PROCESS=true` starts a separate learning worker in the persistent
  Render process. It is enabled by default on Render and never starts on Vercel.
- Alternatively run `python -m app.learning_worker` as a persistent worker.
- Vercel needs database access, not a second copy of the model key: it reads the worker's
  coarse readiness record and queues requests in the shared database. A fixed health
  request wakes the existing Render service after idle suspension; it sends no student
  content or credentials to the health endpoint.
- Browser roles cannot access either learning table. API operations enforce student role,
  active session and notebook ownership. Learning responses disable caching; PDF
  downloads require the same authenticated owner.

Payments and existing student preparation access rules are unchanged. Learning Hub itself
is available to authenticated students and does not introduce checkout or payment gates.

## Verification

Tests cover ownership, role boundaries, duplicate admission, provider unavailability,
source/diagram/depth validation, per-stage recovery, stale leases, real PostgreSQL
concurrent admission, serverless/worker readiness, PDF pagination and content, browser
creation/reading/download, mobile layouts and synchronized deployment assets.
Before release, also run one real researched notebook through every generation stage,
download its complete PDF, visually inspect the pages and verify both deployments serve
the merged commit.
