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
