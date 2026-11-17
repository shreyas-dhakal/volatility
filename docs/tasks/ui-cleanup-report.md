# UI cleanup

User request: clean up the UI, use plain language, add helpful icon colors and use Astryx buttons.

## Changes

- Kept the neutral Astryx theme, with a white workspace and pale navigation rail. Navigation aligns to the left and uses labelled, colored Astryx Icons.
- Plain navigation names: Chat, Files & code, Decisions, Changes, Questions, Designs, Code map. Removed internal tool names from progress text and raw JSON from review details.
- Green check/Approved, amber clock/Needs review, red cross/Not used. Evidence status remains separate from approval; approving a suggestion never silently verifies its source.
- Unavailable actions have grey icons and disabled state. GitHub explains that setup is needed; users can still upload files. Chat and generation actions respect actual server configuration.
- Actual Astryx Button and Icon components remain the controls. Lucide SVG components supply recognizable glyphs through Astryx Icon; no replacement button library.
- Code-map focus and connection searches use named choices instead of asking for internal IDs. Related data and underlying API contracts are unchanged.
- Desktop-only redundant menu controls removed; mobile controls remain accessible, with short action labels.

## Verification

- Frontend suite:21 tests passed, including disabled navigation/GitHub and labelled review-state regressions.
- Next production build and TypeScript checks passed.
- Astryx doctor:20 checks pass,0 failures; existing custom StyleX/font/graph warnings reviewed.
- Impeccable detector returned no findings for changed UI sources.
- Real production proxy smoke passed: accounts, project isolation, uploads, graph import, review history and persistence.
- Actual browser checked at1440×1000 and390×844. Mobile document width390, no horizontal overflow. Rendered navigation actions were confirmed to be actual Astryx buttons with supported icon color tokens.

## Deployment incident

The host disk filled during Docker image deployment, and Docker/Colima storage began returning I/O errors. Removed only this project's620MB disposable Next build cache. With explicit user approval, restarted Colima, preserving database volumes, and restarted affected services. Temporary local production serving was used while Docker recovered. The final app is again served by Docker at http://localhost:3002, with API/database/web healthchecks passing. Saving and persistence were verified after recovery. No unrelated files or database volumes were deleted.

Fresh finish review: **ship at captured scope**, no required fixes or recaptures. See `ui-cleanup-visual-review.md`. Final container rebuild/healthcheck and frontend-proxy smoke passed after the last mobile file-action fix.
