# Clerk development setup

Clerk is the only authentication provider for Galvanise. The web app signs users
in with Clerk, and protected API routes accept Clerk session tokens in the
`Authorization: Bearer` header. The API has no application session-cookie auth.

## Configure local development

Set these values in the private root `.env` file:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` for the Next.js
  Clerk SDK.
- `CLERK_SECRET_KEY` and `CLERK_ISSUER` for API verification and profile lookup.
- `CLERK_AUTHORIZED_PARTIES` as a JSON array of allowed web origins, for example
  `["http://localhost:3000"]`.
- `SOURCE_TOKEN_ENCRYPTION_KEY` to encrypt queued document uploads. Keep it stable while uploads are pending.

`CLERK_JWT_KEY` is an optional PEM public key for local JWT verification;
otherwise the Clerk SDK uses the server key. `CLERK_AUDIENCE` is only needed when
your Clerk session tokens contain an audience. The issuer must exactly match the
Clerk instance used by the frontend. Never commit or print secret values.

The API checks token signature, issuer, authorized party, expiry, not-before,
issued-at, user subject and session ID. It accepts session tokens only from the
bearer header. Clerk profile lookup verifies that users are active and their
primary email is verified. Project ownership remains in Galvanise's database;
Clerk IDs map to stable local owner IDs.

## GitHub repository access

Enable GitHub under **SSO connections** in the Clerk Dashboard. In Galvanise,
select **Settings → Connect GitHub** or sign in with GitHub through Clerk. A
verified GitHub connection on the same Clerk account enables repository selection
under **Files & code**. Users who linked GitHub only through the previous local
OAuth flow need to link it once through Clerk. Existing imports stay available.

With shared development credentials, Galvanise lists the linked user's own
public repositories and uses GitHub's unauthenticated rate limit. To use
authenticated GitHub reads, configure custom GitHub credentials in Clerk.
Galvanise requests provider tokens server-side when listing or importing a
repository and reads public repositories only.

[Clerk GitHub setup](https://clerk.com/docs/guides/configure/auth-strategies/social-connections/github)

## Existing owner records

If an existing local owner has already been linked to a Clerk account, the
reconciliation command checks that the Clerk external ID and verified email
match the local mapping:

```sh
cd apps/api
uv run python -m galvanise.clerk_reconcile --apply
```

Without `--apply`, it reports how many mapped users would be checked and does not
call Clerk. The command never creates Clerk accounts or changes passwords. An
identity mismatch stops reconciliation and requires an operator to resolve it.

## Start and verify

Run the app locally with `./scripts/run-local.sh`. The launcher applies database
migrations before starting the API and web app. Configure both frontend and API
with the same Clerk instance before signing in. Missing Clerk keys show the setup
page and protected API requests fail closed.

API tests use isolated SQLite databases. The Clerk authentication tests verify
locally signed JWTs through the installed Clerk SDK and cover invalid signatures,
issuer, authorized party, time claims, cookie-only requests, account mapping,
owner isolation and identity conflicts. They do not require a live Clerk account.

The frontend uses `@clerk/nextjs` with `proxy.ts`, server-side route protection,
and Clerk's sign-in and sign-up pages at `/sign-in` and `/sign-up`. Account
switches unmount the previous workspace state and in-flight requests.
