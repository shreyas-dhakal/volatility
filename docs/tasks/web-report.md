# Web implementation report

Implemented `apps/web` as a functional Next.js App Router application with Astryx neutral theme, self-hosted Figtree 400/500/600/700 stylesheets, prebuilt Astryx CSS, StyleX compiled using `@stylexswc/nextjs-plugin` (webpack), and React Flow graph exploration. Root npm dependencies and scripts are configured; npm lockfile updated. The unused deprecated official webpack plugin was removed in favour of the plugin explicitly recommended by Astryx for Next.js.

## Working paths

- Session restoration, account registration/login, GitHub login/connect and logout; real cookie-authenticated same-origin API requests.
- Project selection/creation, optional repository, explicit authenticated sample-project seed (no production fake records).
- Persistent conversation selection and creation, streamed delta/tool/error events with abort control and Markdown rendering. New credential/network failures are actionable. Failed sends reconcile persisted messages. Switching projects/conversations is disabled during streams.
- Business TXT/MD/PDF/DOCX upload and extracted document reading, Graphify JSON upload, import activity polling, GitHub public repository list/index.
- Knowledge extraction; approve/reject/correct with expected versions; visible evidence status and history; direct stakeholder answers; decision-to-code evidence retrieval.
- Candidate generation with readable approach, boundary responsibility/contract/evidence/dependency/tradeoff/migration/open-question sections. Design approve/reject, summary correction and readable previous-version history. Scenario comparison uses readable current/proposed sections; selecting an actual graph node sends node_ids to enable grounded structural calculations; empty selection stays qualitative.
- Focused graph filters, bounded 80-node views, actual path lookup, readable node inspection/provenance, keyboard selection. Candidate overlays create labelled React Flow parent groups from actual boundary membership plus readable stable-contract legends. Driver metadata visibly highlights mapped nodes. Business knowledge and boundary nodes inspect locally; technical nodes alone call technical-detail endpoints. Dependency-layer layout prevents the former single-row crisscross display; cycles use a three-column fallback. Edge styling distinguishes explicit verification from unverified upstream/inferred claims. Compact visible relationship labels avoid overlapping annotation text; full evidence status and source confidence remain in edge aria labels and the graph legend/inspector. Controlled graph state uses the supported useNodesState/onNodesChange pair, enabling persistent keyboard selection, with direct pointer inspection too. Pure adapter integration tests consume the actual shipped Graphify fixture and backend-shaped business/boundary overlays.
- Desktop navigation/chat/context layout, mobile menu, project-context action available at every viewport, meaningful server/account settings. No secrets are exposed by the UI.

## Validation

- `npm test`: 4 files, 18 tests passed. Coverage includes cookie requests, multipart headers, API validation/stale-version/offline errors, split-byte UTF-8 and CRLF SSE framing, malformed stream cleanup, missing AI credentials, login/register/error UI and explicit sample-project interaction.
- A graph component event test keeps the real React Flow useNodesState and NodeChangeset implementation, persists Enter selection through onNodesChange, checks technical inspection, then pointer-inspects local business evidence without a technical-node request.
- The sample-project regression test mocks Promise-returning `scrollIntoView` and verifies effects do not return a Promise; this addresses the browser runtime crash found by root.
- `npm run build`: production Next.js 16.4.6 webpack build passed, TypeScript passed, static / and /_not-found generated.
- `npx astryx doctor --built apps/web`: exit 0; 20 pass, 3 warnings, 0 failures. Warnings are external Figtree font stylesheet proof and the explicitly required StyleX carrier/React Flow stylesheet/custom StyleX declarations. Source imports generated root `astryx-themes.js` as required.
- Root coordinator owns runtime browser desktop/mobile inspection and screenshots to avoid duplicate browser work. Foundation notified that web Dockerfile must copy root `astryx-themes.js` before build.

## Limits

- OpenAI and GitHub OAuth success require configured server credentials; frontend does not substitute fabricated responses.
- Graph uses deterministic dependency layers (three-column cycle fallback) with interactive focus/fit/zoom and real edges; it does not claim dependency inference from repository file indexing.
- Figtree is self-hosted through @fontsource/figtree. Layout imports weights 400/500/600/700; a scoped webpack alias ignores the generated module’s external font sheet without modifying that generated file. Built CSS contains local font-face rules and no Google Fonts dependency. Mobile Menu/Send actions cannot shrink; helper text wraps.
- Design summary corrections and review actions are explicit version-checked changes. Boundary changes can be discussed with the architect and reviewed as new proposals.
