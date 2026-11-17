# Chat workspace visual finish review

## Disposition: ship

Ship the chat workspace shown in the supplied desktop and mobile captures. No material visual or usability blocker is visible in these two states. This disposition covers chat only; the architecture graph is outside this review.

## Required material fixes

None identified in the reviewed captures. Recapture is not required for this chat state.

## Evidence checked

- Read `PROMPT.md`, `PRODUCT.md`, `DESIGN.md`, and Impeccable's `reference/craft-floor.md`. Applied the explicit neutral Astryx, typography-first, spacious Operate-mode brief; no approved design comp exists.
- Visually inspected `.impeccable/review/desktop.png` at 1440 × 1000 and `.impeccable/review/mobile.png` at 390 × 844. Desktop keeps navigation, conversation, context, and composer distinct. Mobile wraps header actions, preserves a readable transcript, and keeps the composer and Send action fully visible.
- Text hierarchy, spacing, restrained surfaces, and consistent control treatment suit the requested working interface. The large unoccupied transcript area is appropriate for a one-message conversation. No clipping, overlap, or obstructed primary action is visible.
- The statement explicitly identifies a synthetic scenario; the project title identifies a synthetic demo on desktop. No fabricated AI response or metric appears. Context hypotheses retain visible status labels.
- Parent verification supplied: production captures; Figtree 400/500/600 loaded via `document.fonts`; no horizontal overflow at 390px; detector output `[]`; Astryx doctor has zero failures; registration, sample creation, persistent review/context, keyboard flow, and API proxy exercised. These checks were reported by the parent and were not independently rerun in this review.

## Limits

This is a visual assessment of the two supplied chat screenshots, not a whole-product approval. Static images do not verify measured contrast, focus appearance, hover, streaming, errors, long transcripts, open navigation/context on mobile, or virtual-keyboard behavior. External API credentials were absent in parent testing, so this review makes no live-AI or OAuth claim. Graph and other workspace views require their own checks.

## Optional notes

- Desktop shows both Menu and Close menu while the rail is open. Showing only the currently relevant toggle would reduce redundant chrome; it does not prevent the task.
- The mobile title truncates the synthetic-demo suffix. The visible statement still labels the scenario explicitly, so this is not a provenance blocker; preserving the suffix in a secondary line could improve recognition.
- The context panel repeats the same question under Pending review and Open questions. A future refinement could reduce this repetition while preserving the useful category summaries.

# Targeted graph follow-up

## Disposition: ship reviewed graph state

The supplied final graph capture resolves the targeted readability concerns. No additional fix or recapture is required for this state.

## Required material fixes

None visible within the requested compact-label and layered-layout scope. Node titles remain readable, layers are separated, arrows remain identifiable, and the compact `calls (source)` labels no longer collide with one another or node titles. PurchaseService has a visible selected outline.

## Evidence checked

Visually inspected `.impeccable/review/graph.png`, the actual production 1440 × 1000 capture after Fit View. The technical graph has a clear top-to-middle-to-bottom structure, readable controls and an explanatory legend distinguishing source claims from verification. Parent reports Enter on PurchaseService produced exactly one selected node and the real API evidence inspector (`details: true`), with 18 frontend tests and the production build passing. Those interaction and command results were supplied by the parent, not independently rerun here.

## Limits

This follow-up covers the visible desktop technical graph only. The evidence inspector is below the captured area, so its operation is supported by parent interaction evidence rather than this image. No architecture candidate overlay is displayed or visually approved here; overlay behavior has separate synthetic-fixture tests. Dense graphs, other zoom levels and mobile graph presentation are outside this targeted review.

## Optional notes

Edges share a horizontal routing lane in the upper branch. For this small graph the distinct label positions and visible branch arrows are sufficient; further routing refinement is optional polish.
