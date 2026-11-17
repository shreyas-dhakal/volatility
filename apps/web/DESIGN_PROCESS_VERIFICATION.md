# Design process workspace verification

Task 2 implements the approved `docs/superpowers/specs/2026-11-17-volatility-engine-design.md` API contract in `apps/web`.

The new **Design process** navigation coexists with **Designs**, chat, sources and the code map. It supports structured detailed cases, core cases, independent volatilities, role-classified components with contracts, and qualitative coverage/change-containment proposals. Human review uses the existing records PATCH endpoint with `expected_version`; edits return artifacts to pending review. Generation calls the real API helpers and never auto-approves records.

Reasoning details expose upstream links, downstream consumers, original variations, evidence, version history, collaboration steps and containment scenarios. Deterministic findings retain severity and affected artifact links. Historical or unverifiable input snapshots are labelled explicitly; readiness is never presented as design correctness or executed test coverage. Optional response metadata, including truncation, remains readable.

## Checks (2026-11-17)

- `npm test`: **45 tests passed across 7 files**, including 21 design-workspace tests plus navigation integration coverage.
- `npm run build`: **passed**, Next.js 16.4.6 production webpack compilation, TypeScript and static generation.
- `npx astryx doctor --built apps/web/.next`: **exit 0; 20 pass, 2 warn, 0 fail, 11 info**. Existing theme/font detection warnings refer to Figtree; the application already self-hosts its font in the root layout. No theme changes were made.
- Additional source-folder doctor check: **exit 0; 20 pass, 3 warn, 0 fail, 10 info**. Existing stylesheet/native-markup findings are outside this feature; no raw div/span, new CSS, hex colors or pixel constants were added to the new workspace.
- Impeccable mechanical detector over changed UI: **no findings**.
- `git diff --check`: **passed**.
- Orca browser: inspected the integrated workspace at desktop width and **390 × 844**. Checked existing case review, component responsibilities/contracts and a component-to-volatility reasoning link. Measured document width **390** with no main-region horizontal overflow at 390px. Browser console contained HMR logs and no errors.

Browser checks used an explicitly labelled temporary local API fixture to exercise frontend rendering without credentials. The fixture is not shipped. Live AI calls, backend persistence/owner validation and the combined worker branches still require coordinator integration verification; these checks do not claim those external behaviors were exercised.

## Regression coverage

Tests exercise exact intake/generation payloads, newline normalization, evidence selection, manual intake without AI setup, downstream prerequisite gates, all four generation stages, explicit versioned approval and edits, 409 reload/review behavior, readable upstream/downstream/evidence links, component contracts, stale input versions, deterministic findings, additional truncation metadata, loading/retry and actionable generation errors. A successful save followed by failed refresh is identified as saved, hides obsolete readiness and avoids inviting a duplicate write. Existing cases stay immediately reviewable with explicit expandable intake.

Review was performed by the implementing worker; independent integration review remains Task 3.
