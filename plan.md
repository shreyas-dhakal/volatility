# Galvanise Implementation Plan

**Goal:** Deliver the persistent, authenticated architecture workspace specified in [PROMPT.md](PROMPT.md).
**Architecture:** Next.js App Router and Astryx neutral/StyleX frontend, FastAPI modular backend, PostgreSQL/SQLAlchemy persistence and Alembic migrations. OpenAI runs only on the server. Imported dependencies are structural evidence, never proof of runtime effects.
**Execution:** User authorised independent engineering decisions and multiple Codex sessions. Split non-overlapping frontend, API foundation and intelligence work; integrate and verify after workers report.

## Constraints and review focus

- Never invent AI results, graph edges, integration status or measured savings.
- Every project endpoint and AI tool must enforce ownership. Clerk bearer tokens identify users; GitHub credentials remain encrypted on the server.
- Uploaded/repository text is untrusted evidence. Limit file sizes, retrieval and graph sizes; never execute code.
- Pending AI knowledge cannot overwrite approved records. Reviews and corrections preserve history.
- Missing credentials produce actionable errors. External OAuth/OpenAI end-to-end checks require user-provided credentials; no auth bypass is a production default.
- PostgreSQL is the supported deployment store; SQLite may be used for isolated tests/local smoke checks.

## Tasks

- [x] Save the complete original prompt and inspect the empty workspace.
- [x] Install mandatory Astryx packages, initialise CLI and read every generated instruction/configuration before UI development.
- [x] Establish npm monorepo, Python uv project, environment sample, Docker Compose and API contract.
- [x] Build Clerk authentication, encrypted GitHub OAuth, projects, conversations, persistence and migrations. Test ownership, invalid tokens and CSRF/origin checks.
- [x] Build validated document/repository ingestion, durable job records and safe source retrieval. Test oversized/invalid uploads and secret redaction.
- [x] Inspect a real Graphify export schema; implement normalisation and NetworkX traversal/search/path/scenario functions with fixture tests.
- [x] Build real OpenAI SSE chat, structured extraction, project-scoped tools, volatility, questions, evidence validation, traceability and two candidate designs. Test with mocked SDK responses and no-key errors.
- [x] Build polished Astryx chat workspace, account/project/source flows, knowledge review, contextual panel and focused interactive graph. Include accessible responsive states and frontend tests.
- [x] Provide a clearly labelled, explicit seeded demonstration and reproducible sample requirements/graph.
- [x] Integrate workers; run migrations, backend/API/schema/graph/AI tests, frontend tests and production build; start services and inspect browser flows.
- [x] Document setup, OAuth scopes, Graphify dialect/provenance, limits, test evidence and outstanding external credential checks in README.

## File boundaries

- `apps/api/galvanise/`: config/database/models/security; `routes/`; `services/`; `integrations/`; `agents/`; `graph/`.
- `apps/api/tests/`: backend unit, integration and mocked OpenAI tests.
- `apps/web/`: Next.js application, Astryx components, StyleX styles, API client and frontend tests.
- `packages/shared/`: API contract and cross-session coordination.
- `docs/architecture/`, `docs/decisions/`: evidence, architecture and design decisions.

## Verification

Backend: `cd apps/api && uv run pytest` and `uv run alembic upgrade head`.
Frontend: `npm run test --workspace @galvanise/web` and `npm run build --workspace @galvanise/web`.
Runtime: start PostgreSQL, API and web; sign in through Clerk, create independent projects, upload sample requirements and graph, review knowledge, explore graph, sign out/in and reopen conversation. Validate missing OpenAI/OAuth configuration honestly; run live calls only if credentials exist.

## Execution ledger

- Original brief saved verbatim (21,606 characters). Empty repository created under `galvanise/`; work is on `feat/galvanise-mvp`.
- Astryx 0.7.16 installed and CLI initialised. Generated AGENTS.md/GEMINI.md, neutral theme module and ai-chat template read. StyleX custom-code setup documented by installed CLI.
- Orca launch refused before dispatch with `no_active_sender_terminal`; no Orca workers started. Native Codex agents foundation/intelligence/web are implementing non-overlapping scopes.
- Ruling: omit GitHub `public_repo` scope because it grants write privileges; MVP supports public repositories with identity-only scopes. Private repositories require a future read-only GitHub App.
- No external API credentials available in environment; verify real integrations via mocked boundary tests and actionable missing-configuration errors, and report live-call validation as outstanding.

- Runtime verification: real PostgreSQL migration and schema drift check pass; local runner starts and stops owned app process groups; production Docker API/web images build, all three Compose services healthy on web3002/API8000/DB5433.
- End-to-end smoke passed both direct API and frontend proxy: Clerk bearer authentication, ownership isolation, CSRF/origin block, documents/background jobs, Graphify graph retrieval, synthetic seed, versioned review/stale conflicts and reopen after login.
- Independent code review reproduced/fixed missing persistent answer context and stale same-title proposals; recheck approved. UI verification fixed scrolling-effect promise crash and narrow control truncation; Figtree is locally served and observed loaded.
- External credential requirement remains: live OpenAI completion/GitHub consent need user-provided credentials; no fake production responses implemented.

- Final checks: backend39 tests and frontend18 tests pass; Alembic reports no drift. Production Docker rebuild and all-service healthchecks pass. Final API-proxy smoke passed. Actual keyboard graph selection persists and loads technical evidence; compact labels and focused dependency layout captured.
