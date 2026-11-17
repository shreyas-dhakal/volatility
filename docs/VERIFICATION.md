# Verification record

Build date: 2026-11-17. Results below describe observed checks and their limits.

## Environment

New repository `/Users/shreyas/vol/galvanise`, branch `feat/galvanise-mvp`. Node 22+ (host v24/v26; Docker Node22), uv0.11.7, Python3.12, PostgreSQL17, Docker29.5.2. Astryx core/CLI/neutral0.7.16 installed and initialized before UI work; generated docs, theme configuration and chat template read. Custom styles compile with the documented StyleX Next plugin; Astryx stays prebuilt. Figtree400/500/600/700 is self-hosted, with actual loaded font faces observed in the production browser.

OpenAI and GitHub OAuth credentials were absent. Live model responses and OAuth consent have **not** been verified. Real SDK/API integrations are implemented; tests mock provider boundaries, and runtime checks verify actionable503 errors when credentials are missing. No canned assistant results are substituted.

Orca worker launch rejected before dispatch (`no_active_sender_terminal`); native Codex agents completed independent backend, intelligence and frontend scopes instead. Orca's browser was used for actual application checks.

## Observed results

| Check | Result |
| --- | --- |
| Original prompt | Complete original text saved in PROMPT.md:21,606 characters |
| Backend full suite | `uv run pytest -q`:39 passed in3.01s |
| Frontend full suite | `npm test --workspace @galvanise/web`:18 passed in1.14s across4 test files |
| PostgreSQL migration | `alembic upgrade head` succeeded; current `af78127a72ed`; `alembic check`:no new upgrade operations |
| Production builds | Next webpack + TypeScript build passed locally and in Linux Docker; API image built with frozen uv dependencies |
| Compose runtime | PostgreSQL/API/web each observed healthy, persistent volume retained |
| Runtime smoke | Passed against direct API and frontend proxy, including production containers |
| Astryx doctor | Exit0,20 checks pass,0 failures; warnings reviewed for custom StyleX/ReactFlow styles and generated font sheet; actual local font faces observed loaded |
| Impeccable detector | `detect --json apps/web` returned empty findings[] |
| Independent code review | Two material findings reproduced, fixed and independently rechecked; approved after recheck |
| Chat visual review | Fresh reviewer disposition:ship chat workspace at1440×1000 and390×844; no material blockers |
| Browser state checks | Register account; explicitly seed labelled sample; reopen persisted project after server restart; approve decision to v2; inspect context; graph rendering; keyboard navigation |
| Mobile | Chat viewport390px and document scrollWidth390px; no horizontal overflow; Menu and Send labels remain readable |
| Live OpenAI/GitHub | Not run:external credentials absent |

## Reproduce

```sh
cd apps/api
uv run pytest -q
uv run alembic check
cd ../..
npm test --workspace @galvanise/web
npm run build --workspace @galvanise/web
docker compose up --build -d --wait
python3 scripts/smoke.py --base-url http://localhost:3002 --graph-file examples/wholesale-graphify.json
```

The verified local `.env` uses web3002/API8000/PostgreSQL5433 because an unrelated application occupies3000. Fresh `.env.example` defaults to web3000. Keep WEB_PORT, WEB_URL and the OAuth callback consistent.

The smoke script creates uniquely named accounts/projects without deleting existing data. It checks HttpOnly sessions, unauthenticated denial, cross-project ownership, blocked cross-origin mutation, persistent conversations, missing-provider errors, durable document ingestion, actual Graphify import and bounded graph retrieval, explicit synthetic seed, review history, stale-version409 and sign-out/sign-in recovery. It never calls OpenAI or GitHub.

## Regression evidence

- Browser discovery fixed an effect leaking the Promise returned by newer `scrollIntoView`; regression renders actual sample-entry UI with a Promise-returning mock.
- Direct stakeholder answers now survive old conversation history and large sets of later proposals in bounded AI context.
- Regenerated same-title designs retain revised content in pending records with supersedes lineage; approved predecessors remain intact.
- Technical mappings reject invented/cross-project IDs and preserve retrieval provenance.
- Chat supports up to12 bounded provider rounds so context retrieval plus multiple knowledge tools can finish with an answer; hitting the cap emits an error without a fake completion.
- Graph boundary groups/driver highlights/evidence labels tested with actual Graphify fixture and backend-shaped overlays. Controlled node state and technical/business inspection have component regression coverage.
- Docker ignores local credentials, macOS virtualenvs and generated build directories. Linux image builds include required theme and fixture files.

## Artifacts and remaining limits

Chat captures: `.impeccable/review/desktop.png`, `.impeccable/review/mobile.png`. Review reports: `docs/tasks/final-review.md`, `docs/tasks/visual-review.md`. Detailed implementation reports are alongside them. Final graph capture is `.impeccable/review/graph.png`. After the targeted fixes, actual keyboard selection returned selected-node count1 and the API-backed evidence inspector was present; compact edge labels remained readable. All final production proxy smoke checks passed again.

Private GitHub repositories, teams/SSO, OCR, vector retrieval, distributed job workers and automated stakeholder outreach are outside this MVP. Deployment supports one API worker. Imported dependency claims do not establish runtime behaviour, measured savings or verified business ownership.
