# Workflow migration verification

The feature is in the existing Galvanise workflow detail. A persisted project-owned migration stores source selections, scenario drafts, job results, one approved source-pinned baseline and accepted patches. The API uses the existing Clerk ownership checks and worker lifecycle. Setup, capture and replay instructions are in [Migrate this workflow](../WORKFLOW_MIGRATION.md).

## Paths

- UI entry and results in `apps/web/components/engine-revision.tsx` and `apps/web/components/workflow-migration.tsx`.
- Authenticated workflow API in `apps/api/galvanise/routes/migration.py`.
- Evidence search, durable actions, disposable runner, comparison, coding agent and replay CLI in `apps/api/galvanise/migration/`.
- Schema migration in `apps/api/alembic/versions/420ca617af43_workflow_migration.py`.
- Regression and Docker integration checks in `apps/api/tests/test_workflow_migration.py`.

## Checks

```sh
npm test
npm run build
npx astryx doctor --built apps/web
npm run test:e2e --workspace @galvanise/web
git diff --check
```

The web suite passed 59 tests. The Next.js production build passed. Astryx reported 22 passes, zero failures and one workspace-wide styling warning. The existing browser suite timed out at 90 seconds and its test process was stopped. This shell had no signed-in Clerk storage-state file. Product acceptance remains with the user.

The Docker integration regression used a local Python image with Redis built for the test:

```sh
test_dir=$(mktemp -d)
docker build -t galvanise-workflow-replay-test -f - "$test_dir" <<'DOCKERFILE'
FROM galvanise-api:latest
RUN apt-get update && apt-get install -y --no-install-recommends redis-server && rm -rf /var/lib/apt/lists/*
DOCKERFILE
rmdir "$test_dir"

cd apps/api
GALVANISE_TEST_REPLAY_IMAGE=galvanise-workflow-replay-test GALVANISE_TEST_REPLAY_REDIS=1 \
  .venv/bin/pytest -q -rs
.venv/bin/ruff check galvanise/migration galvanise/routes/migration.py galvanise/main.py \
  alembic/versions/420ca617af43_workflow_migration.py tests/test_workflow_migration.py
.venv/bin/ruff format --check galvanise/migration galvanise/routes/migration.py galvanise/main.py \
  alembic/versions/420ca617af43_workflow_migration.py tests/test_workflow_migration.py
.venv/bin/python -m galvanise.migration.replay --help
```

The API suite passed 221 tests with two opt-in live checks skipped. Targeted Ruff lint and format checks passed. The Docker test captured a real SQLite pre/post state, the actual loopback HTTP requests, one Redis message with destination and payload, and a worker drain. Two legacy runs matched. The replacement returned the same payload and final database state, while one extra outbound request caused the comparison to fail at `/steps/0/http/count` with counts 1 and 2. The test also exercised an authenticated baseline approval, rejected changing the approved scenarios, exported and replayed the baseline, replayed the target difference, and replayed the reduced case.

A temporary PostgreSQL 17 container ran Alembic upgrade, check, downgrade and re-upgrade. Head was `420ca617af43`, and both checks found no new upgrade operations.

```sh
pg_test_id=$(docker run --rm -d -e POSTGRES_PASSWORD=workflow-test -p 127.0.0.1::5432 postgres:17-alpine)
trap 'docker stop "$pg_test_id" >/dev/null' EXIT
until docker exec "$pg_test_id" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
pg_address=$(docker port "$pg_test_id" 5432/tcp)
cd apps/api
export APP_ENV=test
export DATABASE_URL="postgresql+psycopg://postgres:workflow-test@$pg_address/postgres"
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic check
.venv/bin/alembic downgrade bfa4d2219e05
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

Live OpenAI scenario and coding-agent calls were outside development verification. No GitHub push or draft PR was performed. Operational replay for a real project still requires its Git revision, image and hooks in the operator registry. Graphify and source searches produce bounded candidates for engineering review. Input reduction tries a bounded set of removals and keeps only cases reproduced by real captures on both sides.
