# Foundation implementation report

Implemented the assigned backend foundation in the shared checkout. No commits or staging were performed.

## Delivered files and behavior

- `apps/api/pyproject.toml`, `uv.lock`: Python >=3.12, complete API/intelligence dependencies and dev tooling; resolved and installed using uv/Python 3.12.13.
- `galvanise/config.py`, `database.py`, `models.py`: root/local environment loading, production secret/secure-cookie checks, PostgreSQL runtime + isolated SQLite support; complete contract models and single-table knowledge subclasses, all UUID-string IDs, durable sessions/OAuth states/accounts/jobs.
- `security.py`, `dependencies.py`, `routes/auth.py`: Argon2 local registration/login; hashed random server sessions with HttpOnly/SameSite cookies and expiry; unsafe request Origin/Fetch Metadata checks; encrypted account tokens; GitHub OAuth single-use hashed, browser-bound state with 10-minute expiry and row locking; explicit account-linking safeguards, verified primary email and rejection of email-based automatic linking.
- `routes/projects.py`, `records.py`: project/conversation persistence and ownership, message retrieval; atomic expected-version reviews with complete previous snapshots and stale-update 409.
- `integrations/github.py`, `routes/sources.py`, `services/ingestion.py`: real GitHub API listing/tree/blob retrieval, public repos only, no checkout/execution; encrypted durable upload queue, recovery of interrupted jobs; bounded TXT/MD/PDF/DOCX extraction with secret redaction and safe job responses. Extraction is isolated in a spawned process with 20s wall limit, 12s CPU limit and Linux 768MiB address-space limit. Repository graph contains real file nodes and zero inferred edges. Queue payload is scrubbed after completion/failure.
- `main.py`: foundation routers and intelligence router registered under `/api`, intelligence before projects; no blanket suppression of intelligence import errors; explicit local create_all only, normal migration-driven runtime; background persistent queue consumer.
- `alembic.ini`, `alembic/env.py`, `alembic/versions/af78127a72ed_initial_schema.py`: complete static initial migration for all contract/auth tables.
- `.env.example`, `docker-compose.yml`, `apps/api/Dockerfile`, `apps/web/Dockerfile`, `README.md`: all-service Compose healthchecks, persistent PostgreSQL at configurable localhost5433, source-layout-preserving API container for fixture demo, setup/environment/OAuth/security/ingestion/testing documentation. Web Dockerfile copies root Astryx theme configuration and runs production Next build/start with build-time internal API_URL. Published web/API ports are configurable.
- `tests/test_foundation_api.py`, `tests/test_foundation_security.py`: real SQLite/API behavior tests for ownership, CSRF, sessions, history/conflicts, encrypted/redacted ingestion, resource isolation, expanded archive rejection, recovery, OAuth state/scope/email-linking checks and file size limits.

## Verification

- Initial RED: foundation test collection failed with missing `galvanise.main`; the extraction isolation test later failed with missing `extract_bounded` before that feature was written.
- Final complete suite: `cd apps/api && uv run pytest -q` → **33 passed in 2.00s**, exit 0 (intelligence tests concurrently added by its owner).
- Scoped foundation suite: **12 passed**, exit 0.
- `DATABASE_URL=sqlite:////private/tmp/galvanise-foundation-migration.db uv run alembic upgrade head` → exit 0; `uv run alembic check` → **No new upgrade operations detected**, exit 0.
- Foundation production file static check `uv run ruff check --select F,I ...` → **All checks passed!** The broader inherited workspace Ruff style profile reports additional framework/style conventions (e.g. FastAPI Depends defaults and SQLAlchemy mapper class dicts); no claim of full repository style-profile compliance.
- `docker compose config --quiet` → exit 0. Images were not built by this worker.
- Coordinator separately reported live PostgreSQL migration/current/check and credential-free account/upload/CSRF/ownership/missing-key smoke passed. Coordinator owns final runtime integration evidence.

## Boundaries and limitations

- No live GitHub OAuth or OpenAI calls were validated: no credentials were supplied. Missing configuration produces actionable errors.
- OAuth scopes are **read:user user:email only**, explicitly excluding public_repo because it grants write access. Private repositories require a future read-only GitHub App integration. This is an intentional security correction agreed with the coordinator.
- Run one API process in this MVP. Restart recovery requeues running jobs; multi-process leases/heartbeats are future operational work. Sessions and OAuth states persist in PostgreSQL. Stable AUTH_SECRET is required to decrypt persisted material across restarts.
- Secret redaction is best effort. OCR is not included. Parsing isolation has Linux memory limits and cross-platform time/CPU limits; it is not a comprehensive OS security sandbox.
- GitHub listing is bounded at 1000 repositories; ingestion caps 3000 file nodes and 300 text files/3MB selected text. Excluded secret paths and generated/vendor folders are not indexed. Full structural dependency edges require Graphify import.
- Public production deployment requires shared rate limiting, HTTPS/proxy configuration and operational monitoring as documented.

## Deployment context follow-up

Added root `.dockerignore` after coordinator's actual Docker build revealed host `.venv`/`.next` files in build contexts. Local environment files, Git metadata, installed dependencies, generated builds, caches, screenshots and SQLite artifacts are excluded. Source, migrations, root Astryx theme, lockfiles and `examples/` fixtures remain included. API runtime commands now specify `uv run --frozen --no-dev`, preserving the locked production-only environment. Coordinator owns the clean image rebuild/startup check.

The web image also copies `examples/` to `/app/examples/` before Next compilation, because graph-view test imports are checked by TypeScript during the production build. This preserves the same fixture-relative layout as the source checkout. Coordinator reported the API image rebuilt successfully; final web rebuild/startup remains with the coordinator.
