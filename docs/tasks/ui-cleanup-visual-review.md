# UI cleanup visual review

Disposition: **ship at the captured scope**. No required visual fixes or recaptures.

## Evidence reviewed

Reviewed the changed `apps/web/components/workspace-ui.tsx`, `workspace.tsx`, and `graph.tsx`, the direct Astryx exports in `components/ui.tsx`, `DESIGN.md`, and the Impeccable craft floor. Inspected these production screenshots under `.impeccable/review/ui-cleanup/`:

- `desktop.png`: 1440 × 1000, Chat with navigation, composer and Project notes.
- `review.png`: 1440 × 1000, Decisions with Approved and Needs review states and adjacent actions.
- `mobile.png`: 390 × 844, Files & code, document controls and code-map upload.
- `unavailable.png`: 390 × 844, scrolled Files & code with unavailable GitHub action and explanation.

These captures use explicitly synthetic example data. Their statements and quantities are not product claims or evidence about a real project.

## Findings

The cleanup meets the user's request in these views. Navigation is left aligned and readable, with clear labels such as Files & code, Changes and Code map. The neutral rail separates navigation from the working area, the conversation remains spacious, and the composer is visible at the bottom of the desktop capture. Headings, body copy and supporting explanations have a clear hierarchy without decorative card scaffolding.

Icon color now communicates useful distinctions. Blue identifies common navigation and editing actions, purple identifies decisions/designs, and teal identifies code-map actions. More importantly, the decision screen pairs a green check with Approved, an amber clock with Needs review, and a red X with Leave out. Color is reinforced by words and distinct icon shapes. Approval and source certainty remain separate: an approved synthetic decision still visibly says Source not confirmed.

The narrow Files & code view fits its captured width. Headings, descriptions, file names and controls wrap without visible horizontal clipping; Open file remains identifiable beside the wrapped document title. Empty upload actions visibly recede in gray. The unavailable GitHub control also uses gray, explicitly says GitHub not set up, and immediately explains the alternative and recovery: upload files now, or set up GitHub later in Settings. This is substantially clearer than relying on disabled styling alone.

Task copy is plain and actionable: Approve, Leave out, Edit, Sources & history, Find related code, Upload document and Open file. Graph source uses named selectors and phrases such as Find a connection rather than asking users to enter node IDs. Graphify and GitHub remain proper names for supported inputs; the synthetic project content retains its own domain vocabulary. This review does not promise that arbitrary imported or generated prose is free of technical language.

The buttons use Astryx directly through `components/ui.tsx`; `NavigationItem` and `GitHubAction` compose that Button rather than replacing it. `AppIcon` uses Astryx Icon with Lucide shapes and semantic colors. Source establishes `aria-current="page"` on active navigation, explicit disabled props, and suppression of the unavailable OAuth link. The visible Decisions focus outline is clear in the capture.

## Required fixes

None within the reviewed captures and source scope.

## Optional polish

- Longer project and conversation names truncate in the compact rail/header. A full-name tooltip could help users distinguish similarly named projects; the current layout remains usable at these sizes.
- A later visual pass could include the graph canvas, mobile Decisions, expanded history and error/loading states to extend coverage. This is additional coverage, not a recapture requirement for the four valid screenshots reviewed here.

## Verification limits

This is a finish review of four static captures plus source, not a full interactive accessibility audit. I did not independently measure computed contrast, test hover or keyboard traversal, inspect dense/long-content graph rendering, or verify every responsive state. Disabled controls are intentionally low emphasis; their visible explanations carry the required meaning.

The parent reports 21 passing frontend tests, passing TypeScript and Next production build, Astryx doctor 20 pass / 0 fail, an empty detector result, a passing actual API-proxy smoke check, and three healthy services after resolving a disk-full/Colima incident. These are reported verification evidence, not rerun or independently observed by this review. No product files were edited and no routine tests were rerun.
