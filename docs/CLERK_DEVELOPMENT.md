# Clerk-only development authentication

Use the existing application `app_3MEbdIf6xt3sJt7mulZI7WMSb6y`, development
instance `ins_3MEbdHY1zAfwUT1lUYMK2vNjdQg`. Never create a replacement app or run
init over this Core 3 integration. There is no local-password or cookie-session
sign-in, compatibility mode, or switch that reactivates it.

The CLI-authenticated operator provisions development keys directly to ignored
files, without displaying their contents:

```sh
npx -y clerk@latest link --app app_3MEbdIf6xt3sJt7mulZI7WMSb6y
npx -y clerk@latest env pull --app app_3MEbdIf6xt3sJt7mulZI7WMSb6y --instance dev --file apps/web/.env.local
npx -y clerk@latest env pull --app app_3MEbdIf6xt3sJt7mulZI7WMSb6y --instance dev --file apps/api/.env
```

Next needs its publishable and secret keys before building. The API loads its
server key when launched from `apps/api`. Set these nonsecret API values through
the host (use the actual web port):

```text
CLERK_ISSUER=https://main-monkey-9841.clerk.accounts.dev
CLERK_AUTHORIZED_PARTIES=["http://localhost:3002"]
WEB_URL=http://localhost:3002
```

Keep the original `AUTH_SECRET` unchanged: existing GitHub source credentials
are encrypted with it. Preserve the source OAuth client, callback and token
ciphertext independently of Clerk's GitHub social connection. Browser API calls
require a Clerk bearer session token for JSON, multipart and SSE. Only source
OAuth state uses an application cookie. GitHub source linking begins with an
authenticated POST; the single-use callback capability links only that existing
owner and never creates a user or sign-in session.

Run Next with hostname `localhost` when WEB_URL uses localhost. Binding Next to
127.0.0.1 while serving localhost causes Clerk's same-URL internal rewrite to be
network-proxied back to itself in this Next release. `scripts/dev.py` now derives
the web binding from WEB_URL. API binding may remain 127.0.0.1.

Run `uv run alembic upgrade head` from `apps/api`. The latest migration drops only
the obsolete `sessions` table; UUID ownership, projects, source credentials and
unmigrated password digests remain. A downgrade restores an empty table, never
old authenticated sessions. Stored password digests are offline migration data
only; no runtime password hashing/verification or password routes remain.

## Bounded user migration and recovery

Real-user bulk import still requires a separately confirmed target and window.
The offline tool defaults to a read-only preflight:

```sh
uv run python -m galvanise.clerk_import
```

The explicit development apply option imports original compatible Argon2 digests,
reserves unverified emails, uses the unchanged local UUID as external_id, and
checkpoints the Clerk subject locally. It reconciles ambiguous retries and blocks
conflicts instead of merging by email. `argon2-cffi` remains for import-format
parsing and synthetic tests; the live authentication path never uses it.

A verified Clerk email alone does not prove ownership of an old locally
unverified email. For a single blocked owner, an authorized operator must first
establish original ownership using independent evidence, inspect only the
required owner/subject metadata, and confirm the exact pair. Check that the
Clerk user is not banned/locked, its verified primary email matches, and neither
subject nor external_id maps elsewhere. Set its external_id through the selected
development app's Backend API, then conditionally write `users.clerk_user_id`
for the unchanged local UUID. Recheck the remote identity and project owner/count.
Do not read hashes/tokens, merge UUIDs, run a bulk import, or add a public recovery
endpoint. The coordinator performed this bounded one-owner recovery for the
user; that action does not authorize linking other existing users automatically.

## Verification

```sh
APP_ENV=test DATABASE_URL=sqlite:// uv run pytest
npm test
npm run build
npx astryx doctor --built apps/web
```

Tests force disposable databases and disable environment-file loading. Domain
tests mock only the external identity boundary; separate tests pass locally
signed tokens through the real Clerk SDK. The API rejects old cookies and old
password routes regardless of obsolete environment flags. Missing Clerk keys
show a setup-needed page without invoking accountless setup. Live development
credentials are kept out of test logs, commits and chat.

`scripts/smoke.py` uses two current synthetic Clerk tokens supplied through
`GALVANISE_SMOKE_TOKEN` and `GALVANISE_SMOKE_OTHER_TOKEN`, never CLI arguments.
Run it only against an isolated database; it creates test projects, not users.
Live OAuth-provider consent and production configuration are separate from the
Clerk-only code cleanup and are not inferred from passing isolated tests.
