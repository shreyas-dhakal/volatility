# Galvanise

Persistent AI architecture workspace: local accounts, GitHub public repository indexing, bounded document ingestion, Graphify import, real OpenAI streaming, versioned knowledge review and grounded architecture exploration.

## Local setup

Requires Node.js 22+, uv (Python 3.12+), Docker and PostgreSQL 17. From the repository root:

```sh
cp .env.example .env
# Set AUTH_SECRET to a random secret (for example: openssl rand -hex 32).
# Add OPENAI_API_KEY to enable real AI; leave blank to see actionable configuration errors.
npm ci
cd apps/api
uv sync --python 3.12
cd ../..
docker compose up -d --wait db
cd apps/api
uv run alembic upgrade head
cd ../..
./scripts/run-local.sh
```

Open the URL printed by the runner (http://localhost:3000 by default; this verified workspace uses http://localhost:3002 because 3000 is occupied). Register an account and create a project. Local registration requires a password of at least 10 characters. PostgreSQL listens on **5433**, configurable with POSTGRES_PORT; keep DATABASE_URL consistent. Runtime migrations are mandatory. `AUTO_CREATE_TABLES=true` is an explicit local/test convenience only.

Run manually in two terminals if preferred:

```sh
cd apps/api && uv run uvicorn galvanise.main:app --reload --host 127.0.0.1 --port 8000
# Separate terminal at root:
npm run dev --workspace @galvanise/web
```

`docker compose up --build -d --wait` runs all three services with persistent database storage and healthchecks. The web image builds and serves the production Next application. Set WEB_PORT/API_PORT to change published ports, and update WEB_URL plus GITHUB_CALLBACK_URL to match the browser origin. The Compose build fixes the internal API rewrite to http://api:8000. Keep `WEB_PORT` consistent with `WEB_URL` and `GITHUB_CALLBACK_URL` in `.env`; `API_PORT` defaults to 8000. Do not delete the database volume when upgrading; use Alembic migrations.

## Configuration and accounts

Copy `.env.example` to `.env`. Root `.env` loads into the API. `OPENAI_MODEL` defaults to `gpt-5.5`; choose a model available to your account that supports responses/structured outputs. Model credentials are server-only. Missing credentials return HTTP 503; no generated AI answer is simulated. OpenAI sends only bounded retrieved context, though it remains an external data processor.

`AUTH_SECRET` encrypts GitHub credentials and queued uploads; keep it stable across restarts and back it up securely. Only development/test may generate an ephemeral secret when omitted; restarting then invalidates stored encrypted material. Production (`APP_ENV=production`) requires a secret of at least 32 characters and `COOKIE_SECURE=true`, HTTPS and a matching `WEB_URL`. Cookies are HttpOnly, SameSite=Lax; unsafe requests check Origin and Fetch Metadata. Deploy behind a trusted proxy; add shared rate limiting and operational monitoring before public multi-tenant use.

Create a GitHub OAuth App. Use homepage `http://localhost:3000` and callback `http://localhost:3000/api/auth/github/callback`; set `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_CALLBACK_URL`. OAuth requests **read:user user:email only**. The MVP lists connected-account public repositories (up to 1,000) and indexes them using tree/blob GET requests. Private repositories are rejected; a future GitHub App must provide read-only Contents permissions. `public_repo` is deliberately excluded because it grants repository write access. Existing local accounts must sign in before connecting GitHub; matching email alone never links accounts.

GitHub tokens are encrypted at rest; random session tokens and OAuth states are stored only as hashes. Jobs and account responses never expose token ciphertext or uploaded raw bytes. GitHub/OpenAI error responses contain no provider credentials.

## Ingestion and review

### Versioned design from chat

Upload a project’s requirements or source files in its workspace, then select **Design
system** or send “Design this system” in chat. Galvanise uses volatility-based
decomposition, based on the approach in Juval Löwy’s *Righting Software*. It traces
core outcomes through proposed contracts and tests which components would need to
change under a hypothetical business change.

Open the design view to inspect source coverage, the evidence behind observed
decisions, component responsibilities, dependencies and walkthroughs. An excerpt
opens with its source locator. Questions about the published revision are read-only.
To change it, send “Correction: …” or select **Apply as correction** on a user
message. The previous revision remains available while the worker prepares the new
one. The diff identifies affected records.

Choose **Plan project** on a published revision to generate activities. Supply
efforts, skills, a start date and staffing to calculate a schedule. Add rates for
cost and alternative rosters to compare staffing options. The critical path uses
dependencies alone. The scheduled finish also accounts for individual availability
and commitments. The planner reports feasible estimates on a five-day workweek.

Set `OPENAI_API_KEY` on the API server. The design stages use `DESIGN_MODEL` when
configured and otherwise use `OPENAI_MODEL`. Apply the database migrations and
start the API with its background worker using the local setup above. For local
password authentication on both the web app and API, start the launcher with
`AUTH_MODE=legacy ./scripts/run-local.sh`. For Clerk, follow the [Clerk setup
guide](docs/CLERK_DEVELOPMENT.md).

#### Verify the versioned engine

Run the fixture suite from `apps/api` with `uv run pytest`. Run the full-stack
Chromium test from the repository root with
`apps/api/.venv/bin/python scripts/e2e_design/run.py`. It exercises uploads, the
design worker, evidence inspection, correction, revision history and reload in an
isolated database. [Browser test prerequisites](scripts/e2e_design/README.md)

To inspect the real model’s behavior on a synthetic parking brief, run this from
`apps/api` with the server model configuration in the environment or `.env`:

```sh
RUN_DESIGN_LIVE=1 DESIGN_LIVE_REPORT=../../test-results/design-live.json \
  uv run pytest -q -s tests/test_engine_live.py
```

The JSON records intermediate citations, repair attempts, the published revision
or failure, and a separate model assessment of grounding, unsupported variability
and predicted change impact.

### Guided system design

Open **Design process** in a project to work from gathered use cases toward a
reviewed system design. Source code is optional:

1. Record detailed use cases, including actors, steps, outcomes and variations.
2. Propose and review core cases that express the business essence and retain
   explicit links to the original cases.
3. Identify independent reasons for change over time or across customers.
4. Propose components that hide those changes behind stable contracts, separating
   client, manager, engine, resource access, resource and utility responsibilities.
5. Review proposed collaborations and change-containment scenarios alongside
   deterministic coverage, reference, dependency and freshness findings.

Each AI stage is explicitly requested and produces pending proposals. Review and
approve current inputs before progressing. Changes to upstream design records or
referenced versioned evidence make dependent reasoning stale; regenerate and review
it. Pending or stale component dependencies block their consumers from being usable
validation inputs. Context omissions and excerpts are reported rather than hidden.

Approval and readiness do not establish architecture correctness or executed test
coverage. Source documents, messages and external state have no version snapshots;
live model behavior and PostgreSQL concurrency remain outside the isolated checks.
See the [engine API guide](apps/api/README.md),
[review fixes](apps/api/REVIEW_FIXES.md), and
[independent integrated review](docs/reviews/2026-11-17-volatility-engine-independent-review.md).

Upload TXT, MD, PDF or DOCX, up to 10 MiB (`MAX_UPLOAD_BYTES`). Extracted text is limited to 300,000 characters; PDF supports at most 200 pages and no encryption; scanned PDFs require OCR outside this MVP. DOCX expanded archive content is limited to 20 MB. Parsing runs in a separate process with a 20-second wall timeout and CPU limits; Linux additionally enforces a 768 MiB address-space limit. Secret-like assignments, common tokens and PEM private keys are redacted. Redaction is best effort; do not upload credentials.

Ingestion jobs persist in PostgreSQL and are consumed by the API's background thread. Interrupted running jobs return to queued on restart; run **one API process/worker** in this MVP. Job status is visible in the workspace; failed jobs retain a safe error message and users can resubmit. Raw queued upload material is encrypted and removed when complete or failed. Repository ingestion never checks out or executes code. It indexes up to 3,000 file nodes and a bounded selection of 300 text files, with zero invented dependency edges; import Graphify for structural relationships.

All imported content is untrusted evidence. AI proposals begin pending; explicit review uses optimistic version checks (409 on stale review), with prior snapshots retained. Evidence labels distinguish verified, human confirmed, AI inferred and hypothesis records.

## Graphs, demo and tests

See [Graphify schema and provenance](docs/architecture/graphify.md). Import a Graphify JSON export in Files & code; real edges support search, focus, node details and dependency paths. Use the workspace's explicit demonstration action to create labelled synthetic business records and an actual sample graph. Demo content never pretends to be a live integration. Sample inputs are in `examples/`; seed is also available through `scripts/seed_demo.py`.

```sh
cd apps/api
uv run pytest
# Isolated migration check (choose a new temporary filename):
DATABASE_URL=sqlite:////tmp/galvanise-migration-check.db uv run alembic upgrade head
DATABASE_URL=sqlite:////tmp/galvanise-migration-check.db uv run alembic check
cd ../..
npm run test --workspace @galvanise/web
npm run build --workspace @galvanise/web
```

See [verification results](docs/VERIFICATION.md). Automated backend tests use isolated SQLite and mocked AI responses. Live OpenAI and GitHub OAuth require real credentials and are not claimed by credential-free tests. SQLite is for isolated checks; PostgreSQL is the deployment database. Architecture evaluations calculate only grounded structural effects; they do not invent financial savings or runtime behavior from imports.

## Verified local run

The completed build is running at [http://localhost:3002](http://localhost:3002), with API documentation at [http://localhost:8000/docs](http://localhost:8000/docs). All three Compose services have healthchecks. Create your own account, then create a project or choose **Explore sample project**. The saved original request is [PROMPT.md](PROMPT.md); the execution plan is [plan.md](plan.md).

For an integrated runtime check against the frontend proxy:

```sh
python3 scripts/smoke.py --base-url http://localhost:3002 --graph-file examples/wholesale-graphify.json
```

The local runner can create `.env` with a stable random secret on first start when it is absent. It starts PostgreSQL, installs missing dependencies, migrates the database and supervises the API/web processes. Ctrl-C stops only the app processes it owns. Docker PostgreSQL persists independently. Stop production containers with `docker compose stop api web` before starting the development runner on the same ports.

## MVP boundaries

Projects have one owner; team membership and organisation SSO are not implemented. GitHub supports public repositories with identity-only OAuth scopes; private repositories need a future read-only GitHub App. Only GitHub is exposed as an account integration. Repository indexing is a bounded file/text index; it is not a code-execution or dependency-extraction engine. Graphify supplies explicit structural relationships.

Retrieval is bounded lexical/context retrieval, not an embedding index. Graph and document size limits prevent indiscriminate repository submission. Long graph imports remain synchronous within the strict 10 MiB/20,000-node/60,000-edge caps; document and GitHub ingestion use durable jobs. One API process is supported by the current restart-recovery worker. PDF OCR, automated stakeholder email, code modification, cost predictions, production autoscaling and exhaustive semantic program analysis are outside this version.

OpenAI streaming and structured workflows are real SDK integrations; live calls and OAuth consent still need your own credentials in `.env`. After adding credentials, run `docker compose up -d --force-recreate api` to reload server configuration. Never commit `.env`.

Chat tool execution is capped at12 provider rounds per message. This allows context retrieval, multiple pending knowledge records and a final answer while bounding runaway tool execution. Provider failures and cap exhaustion are reported; partial assistant output is labelled and persisted when present.
