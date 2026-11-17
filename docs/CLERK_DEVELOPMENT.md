# Clerk development migration

This migration uses the existing application's development instance:
`app_3MEbdIf6xt3sJt7mulZI7WMSb6y`. Never create or relink to another app.
The migration plan is approved for development integration and isolated tests;
real-user imports and production cutover still require separate confirmation.

## Server configuration

Provision configuration in the host, without putting values in source control or
pasting secrets into agent chat. The API uses `AUTH_MODE=clerk` by default.
`AUTH_MODE=legacy` is the coordinated rollback mode; it must agree across tiers.

The API needs `CLERK_SECRET_KEY` for authoritative user lookup/provisioning,
`CLERK_ISSUER` containing the exact development frontend API origin, and
`CLERK_AUTHORIZED_PARTIES` containing a JSON array of the permitted web origins.
`CLERK_JWT_KEY` is an optional public PEM for offline signature verification;
otherwise the SDK fetches and caches verification keys using the server key.
`CLERK_AUDIENCE` is optional, only when the issued session tokens use an audience.
Do not configure it to an unrelated token template. Session verification checks
issuer, authorized party, expiry, not-before, issued-at, subject and session ID,
and accepts only session tokens sent in the Authorization bearer header.

Keep `AUTH_SECRET` unchanged: source tokens in `accounts.token_ciphertext` depend
on it. Clerk sign-in does not replace repository authorization, the source OAuth
client or its existing callback. `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`,
`GITHUB_CALLBACK_URL` and `WEB_URL` retain their source-integration purpose.
Clerk's GitHub social provider is configured separately in the selected instance.

Both tiers must use the same Clerk instance. Missing API configuration fails
closed; installing the frontend SDK alone does not complete the migration.
Offline token verification can accept a revoked session until its short-lived
JWT expires; user bans/locks are checked via the authoritative user lookup on
each API request. Review session-lifetime needs before production rollout.

## Migration tooling

Run from `apps/api` using an operator-managed database connection. These commands
are not startup hooks and must not run against real users without approval:

```sh
uv run alembic upgrade head
uv run python -m galvanise.clerk_import
```

The second command is a read-only preflight: no Clerk calls and no exported user
records. It reports total/ready/blocked/migrated counts. It checks normalized email
collisions and supported Argon2 encoding; null passwords require an existing
GitHub connection. Any blocked user prevents the entire apply batch.

After separately confirming the exact development database, instance and window:

```sh
uv run python -m galvanise.clerk_import --apply --confirm-development-import
```

The command requires `APP_ENV=development` and a development secret key. It
imports original hashes, reserves unverified emails, sets `external_id` to the
local UUID, and persists `users.clerk_user_id`. It reconciles by external ID before
retrying ambiguous failures, honors rate-limit backoff and never merges by email.
The database mapping is its durable checkpoint. Retry the same command after
interruption; resolve identity conflicts manually, never overwrite a mapping.
Output contains counts or redacted errors, never hashes, tokens or full records.

First prove import/sign-in with synthetic users in the selected development
instance. OAuth-only users need email verification and Clerk account linking;
source tokens stay local. Changed/inaccessible emails require independently
verified recovery. Test both before any real-user import.

After the agreed maintenance freeze, final delta import, ownership reconciliation
and coordinated Clerk-mode deploy, optionally remove old session rows:

```sh
uv run python -m galvanise.clerk_cutover
uv run python -m galvanise.clerk_cutover --apply --confirm-development-cutover
```

Dry-run is the default; apply requires development and Clerk mode. Old cookies
are rejected in Clerk mode even before row cleanup. This command does not revoke
Clerk sessions, change deployment mode, delete password hashes or touch GitHub
credentials. Users must sign in again. Browser sign-out must call Clerk signOut;
the old `/api/auth/logout` endpoint only removes the legacy cookie/session.

## Verification without account access

```sh
APP_ENV=test DATABASE_URL=sqlite:// AUTH_MODE=legacy uv run pytest
```

Tests force an isolated in-memory database and disable environment-file loading.
Existing domain fixtures explicitly exercise legacy mode; Clerk tests switch mode
and pass real locally signed tokens through the installed Clerk SDK. They cover
invalid signatures/times/issuer/origins, source linking, legacy-cookie rejection,
owner isolation, migration retries/conflicts, and reserved-email payloads. These
tests do not establish live instance compatibility or successful host setup.

Do not apply a blind database snapshot rollback after users have created work or
changed credentials. Keep the write freeze until the rehearsal passes; otherwise
reconcile Clerk-only users and changed credentials or forward-fix. Retain the
additive mapping and source encryption material through the rollback window.
