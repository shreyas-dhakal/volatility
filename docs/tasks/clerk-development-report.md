# Clerk-only cleanup verification

The application now authenticates exclusively with Clerk. Removed backend
password registration/login/logout handlers, cookie-session issuance/verification,
Session ORM model, obsolete cleanup command, frontend password form, all mode
switches and sign-out/request fallbacks. The old environment flag cannot reactivate
local authentication. Source OAuth is authenticated POST-only and cannot create
owners or sign-in sessions.

The new Alembic migration `19d05c88b712` drops only the obsolete sessions table.
Tests prove owner IDs, projects, source ciphertext and unmigrated password digests
survive. Password digests remain solely for offline import; argon2-cffi is used
only for import-format parsing and synthetic migration tests, never runtime login.

## Exact checks

- Backend suite: **133 passed**, including real signed-token SDK verification,
  removed routes, rejected cookies/obsolete mode flag, migration preservation,
  source-link ownership/replay, domain authorization/ingestion/design regressions.
- Frontend suite: **54 passed** across nine files. Old local-form tests were
  removed; Clerk loading/account change/sign-out, required bearer headers and
  multipart/SSE remain covered.
- TypeScript: pass. Configured Next production build: pass (protected root is
  dynamic, sign-in/up dynamic). Astryx doctor: **20 pass, 3 warnings, 0 failures**;
  warnings cover existing font-proof/source-style findings.
- CLI doctor: login, selected-app link/reachability and development-key checks pass;
  remaining warnings are optional production instance and shell completion.
- Hostname self-proxy regression fixed in `1682ac5`, with regression-first launcher
  test: Next binds the validated WEB_URL hostname rather than hardcoded IPv4.

## Live development evidence

Selected app `app_3MEbdIf6xt3sJt7mulZI7WMSb6y`, development instance
`ins_3MEbdHY1zAfwUT1lUYMK2vNjdQg`, issuer
`https://main-monkey-9841.clerk.accounts.dev`. CLI materialized development keys
directly into ignored environment files; no file contents or keys were displayed.
No init, replacement application, production changes or real-user bulk import ran.

Two generated synthetic users were imported from a disposable SQLite database,
with unchanged UUID/external IDs and reserved email identifiers. The selected
instance accepted the original Argon2 digest and its Backend API verified the
synthetic password successfully. Both synthetic users were deleted and external-ID
absence verified; the temporary credential fixture was deleted. This proves live
hash-import compatibility, not a completed third-party GitHub OAuth consent flow.

Coordinator activated main Clerk services and performed the separately authorized
single-owner recovery after independent operator evidence, preserving the owner's
UUID and existing project. This worker did not alter main configuration, services,
credential rows or that recovery mapping. Main integration/restart is coordinator
owned. Worker services use only disposable data on 3091/8091.

Domain test fixtures now mock the external identity boundary; there are no local
password/session fixtures or production bypasses. The operator recovery procedure
is documented in CLERK_DEVELOPMENT.md; no new public recovery endpoint/tool was
added. Full provider-consent, production configuration and existing-user bulk
migration remain outside this bounded cleanup. Author self-review only; no helper
agents were dispatched.
