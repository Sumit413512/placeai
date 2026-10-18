# PlaceAI design references

Reviewed 15 October 2026. Saved for future design work; no third-party runtime or agent installation was added.

| Reference | Assessment | PlaceAI decision |
| --- | --- | --- |
| https://github.com/nexu-io/open-design | Apache-2.0 design workspace, not a drop-in component library. Its daemon, model integrations and workspace are outside this release. | Keep as a prototyping reference; do not add its infrastructure or dependencies. |
| https://github.com/nutlope/hallmark | MIT design guidance and examples emphasizing intentional composition and avoiding generic templates. | Use as a reference for restraint and product-specific hierarchy; preserve PlaceAI identity and established flows. |
| https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | Design skill and reference data across stacks. | Use its accessibility and consistency principles as reference material, without running its installer or changing agent configuration. |
| https://21st.dev/@shadcn/components/button | Button variants and icon-plus-label patterns. React/Radix dependencies do not match the existing vanilla JS frontend. | Implement native HTML/CSS equivalents with visible text, hidden decorative icons, focus rings and reduced motion. No component source copied. |

## Design decisions

- Preserve white surfaces, blue primary actions, semantic pastel categories and regular Calibri/Carlito typography.
- Use concise, truthful landing copy. Keep the requested headline and Learn / Practice / Get Placed journey.
- Give each journey a restrained decorative emoji; use consistent line icons for workspace navigation and metrics.
- Keep visible labels on actions. Add short task descriptions to dashboard shortcuts rather than decorative content or invented statistics.
- Use one control radius, visible keyboard focus and a minimum 44px primary control height. Preserve existing handlers, routes, permissions, assessments and optional MFA.
- No new external scripts, fonts, UI libraries, AI subscriptions or data transfers. Payments remain deferred.

These references inform design judgment; they cannot guarantee that viewers will not perceive a site as AI-generated.


## Follow-up selection — 16 October 2026

| Candidate | Fit for PlaceAI | Decision |
| --- | --- | --- |
| [Vercel Web Interface Guidelines](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines) | Framework-independent review of working interfaces. | Selected for targeted native HTML/CSS corrections and regression checks. |
| [Taste Skill](https://github.com/Leonxlnx/taste-skill) | Art direction; its default targets public-facing pages, while its redesign variant starts with an existing interface audit. | Supplemental visual reference; retain the approved PlaceAI direction. |
| [Awesome Design.md](https://github.com/VoltAgent/awesome-design-md) | Community collection of brand design references. These are not proof of official endorsement by those brands. | Reference only; no copied company branding or typography. |
| [Image to Code](https://github.com/Leonxlnx/taste-skill/tree/main/skills/image-to-code-skill) | Helpful when a specific reference screen must become working code. | No new reference screen in this task; no image generation pipeline needed. |
| UI UX from Axure | Exact package could not be established from the supplied name. | Not installed or executed; the verified guideline source covers this task. |

The plugin-directory search did not return these exact packages. Public source guidance was reviewed directly; no plugin installation is claimed. No new libraries, accounts or external design runtimes were added.

## Applied guideline findings

- `app/templates/index.html`: add native bypass links and focusable main targets for public and signed-in users.
- `app/templates/index.html`: fix the hero supporting heading from h3 to h2; preserve its visual size.
- `app/static/selected-theme.css`: give anchored sections clearance below the sticky header and balance primary headings.
- `app/static/selected-theme.css`: replace continuous decorative journey motion with a brief, once-only entrance; respect reduced-motion scrolling.
- `app/static/app.css`: replace an implicit all-property button transition with explicit visual properties.

Source: https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md . This focused review is not a certification of complete guideline or WCAG conformance across every workflow. Existing assessment/media, authentication, permissions, payments deferral, typography and logo assets remain unchanged.


## October 18 workspace refinement
See root DESIGN.md for the getdesign.md review, feature-to-reference mapping, shared tokens and functional invariants. Course catalogue and overview use genuine course metadata; operations workspaces share consistent navigation, surfaces and table typography. No reference code or new UI dependency was imported.
