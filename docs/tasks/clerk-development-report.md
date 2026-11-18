# Clerk authentication status

Clerk is the only authentication provider in the current application. Next.js
protects the workspace with Clerk, passes session bearer tokens to FastAPI, and
uses Clerk for sign-in, sign-up and sign-out. The API does not accept local
password credentials or authenticate from browser session cookies.

Local application users retain stable Galvanise owner IDs. Clerk subject IDs map
to those owners, and GitHub repository credentials remain separately encrypted
with `SOURCE_TOKEN_ENCRYPTION_KEY`. A database migration removes local password
hashes and server-session rows from upgraded databases.

Configure the same Clerk instance in the web and API environments, then use
`./scripts/run-local.sh` to apply migrations and start the app. See
[Clerk development setup](../CLERK_DEVELOPMENT.md) for required keys and local
verification steps.
