# Clerk authentication migration implementation plan

> **For the assigned worker:** Execute this plan yourself, task by task, only after the coordinator conveys explicit user approval. Use superpowers:executing-plans; do not dispatch additional agents.

**Goal:** Replace local sign-in and sessions with Clerk across Next.js and FastAPI while preserving every local user, project owner, and GitHub source connection.

**Architecture:** Clerk becomes the identity/session authority; the existing SQL users table remains the application identity and ownership authority. Verified Clerk subjects map to unchanged local user UUIDs. FastAPI authenticates every protected API request independently of Next.js.

**Tech stack:** Existing Next.js 16.4 / React 19, FastAPI, SQLAlchemy/Alembic, argon2-cffi; add the current compatible Clerk Next.js and Python backend SDKs after approval.

**Spec:** Dispatched task `task_a4315c15bc3a`, selected application `app_3MEbdIf6xt3sJt7mulZI7WMSb6y`, and the user-approved setup checklist subject to the separate migration-plan approval gate.

**Status:** Historical proposal, superseded by the user's Clerk-only cleanup requirement: no local sign-in/session code or reactivation mode remains. Approved for development integration and isolated synthetic tests via coordinator message `msg_4a3ead66bf74`; production and real-user imports remain separately gated. The original inspection-only phase is complete. Implementation is underway; host CLI login and live instance validation are pending. No environment/claim files have been read, and no real-user imports or production cutover have run.

## Constraints and approval decision

Approve: (1) additive identity mapping and backend API import, (2) preserving local IDs and encrypted GitHub credentials, (3) a coordinated maintenance-window session cutover requiring users to sign in again, (4) reserved/unverified imports where email verification is not evidenced, and (5) the bounded file integration strategy below. The initial setup-checklist approval does not authorize these steps. Production import/cutover dates and the target instance must be explicitly confirmed before executing them.

Only use the selected existing Clerk application. Never create an accountless/replacement application, list/select other applications, or relink the project. Never read or print environment files or claim files. Provisioning secrets is a host/operator responsibility; no keys, tokens, password digests, database exports, or credential-bearing responses may appear in commits, logs, or chat. No merge into the coordinator branch.

## Inspected baseline and implications

| Evidence in this checkout | Migration implication |
| --- | --- |
| Root and web `package.json`; API `pyproject.toml` | Next.js 16 and React 19; no Clerk SDK declared. API has argon2-cffi and cryptography, with no Clerk SDK declared. No tracked Clerk/proxy/middleware file was found. Recheck before setup in case another change lands. |
| `apps/api/galvanise/models.py`; initial Alembic migration | `users.id` is an application UUID; unique email, name and nullable password hash. `projects.user_id`, accounts and sessions reference that UUID. Do not replace primary keys with Clerk subjects. |
| `security.py`, `dependencies.py` | PasswordHasher defaults generate Argon2 hashes; opaque sessions last 14 days, are SHA-256 hashed in DB, and use an HttpOnly SameSite=Lax cookie. Actual stored hash variants and parameters have not been inspected. |
| `routes/auth.py` | Register/login/me/logout plus GitHub start/callback/repos. GitHub callback currently signs in or links, refuses email collision without prior sign-in, then issues a local session. Local password registration does not verify email. |
| `models.Account`, `integrations/github.py`, `security.py` | GitHub numeric ID and encrypted source access token belong to the local user. Fernet encryption derives from `AUTH_SECRET`; changing/removing that secret would break repository access. |
| `main.py`, `security.check_origin` | Mutating requests have an origin guard; `/api/health` is public. Existing data routers depend on `get_current_user`, and `require_project` compares the owner UUID. |
| Routes `projects`, `sources`, `records`, `intelligence` | Protection includes project CRUD, conversations/messages, uploads/documents, jobs, GitHub ingestion, analysis/chat streaming, graphs, traceability, questions and architecture/evaluation. Keep their authorization contract returning a local `User`. |
| `apps/web/next.config.js`, `lib/api.ts` | `/api/*` rewrites to FastAPI. Both JSON/multipart requests and SSE chat currently send cookies, without bearer tokens. |
| `app/layout.tsx`, `app/page.tsx`, `components/workspace.tsx` | Root client workspace bootstraps from `/auth/me`, renders local auth and signs out through the API. Root layout has no ClerkProvider. Current config does not enable Cache Components. |
| Foundation/security/intelligence tests and web auth/API tests | Existing tests exercise local registration/session fixtures, expiry, ownership, OAuth state and encryption. Replace fixtures deliberately while keeping source, ownership and intelligence regressions. |

No real user counts, email verification history, stored hash formats, selected application settings/instance, CLI authentication, GitHub provider configuration or live migration feasibility are established by this inspection. These are explicit execution preflights, not claims that the app is migration-ready.

## Identity and import design

Use an additive nullable unique `users.clerk_user_id` column (Clerk subject). Keep all `users.id` values and foreign keys. For existing users import with `external_id = users.id`; persist the returned subject in the local column. Resolve each authenticated request by the verified subject and this database mapping. Never accept ownership IDs supplied by the browser or resolve legacy users by an unverified email or user-editable metadata. No custom token claim is required.

For new Clerk sign-ups, a transactional provisioner loads the authoritative Clerk user through the server SDK, generates a local UUID, creates the mapping once, and sets the Clerk external ID to that UUID. If the external-ID update fails, deny data access until reconciliation succeeds; retry against the existing mapping rather than create another user. Database uniqueness handles concurrent first requests. Conflicts with an existing local email are blocked for explicit account recovery, never silently merged. Local name/email synchronization must not change ownership; an email collision leaves the mapping intact and surfaces recovery.

Implement a backend-only import command with dry-run and apply modes, reading through the database connection without dumping rows. It emits counts and redacted categories, with a private checkpoint store for per-user reconciliation. Dry-run checks null/unsupported hashes, duplicate normalized emails, mapping conflicts, and optional GitHub-only users. Apply calls Clerk Backend API `POST /v1/users` (SDK equivalent), then persists the mapping. Before every create/retry, reconcile `external_id` against the selected instance; an ambiguous timeout must not duplicate a user. Back off on 429/Retry-After and transient failures, checkpoint progress and stop on conflicts. Do not overwrite an existing Clerk user's password or attach a matching email without ownership evidence.

Password users: pass the original encoded hash as `password_digest` with `password_hasher` matching its actual prefix (`argon2id` or `argon2i`); do not rehash a digest or obtain plaintext. Clerk documents both variants, but require a synthetic hash generated with this project's installed hasher parameters to import and sign in successfully before processing real users. Unexpected formats block that user's migration; use an explicitly approved password-reset recovery path rather than silently dropping credentials. Source inspection suggests compatibility, not proof of real-record compatibility. [Create user reference](https://clerk.com/docs/reference/backend/user/create-user)

Email assurance: local password accounts have no verification evidence. Import them as reserved/unverified using the current Backend API identification-status option; its default verified behavior is unsuitable. Test the reserved-email/password/verification flow in the target development instance. GitHub-only users have no password; omit digest fields and use the API's password-requirement bypass only for that migration case. A linked GitHub account alone does not prove the local user's email was verified (password users can link later); only mark an email verified with separate trustworthy evidence. Otherwise require verification. If the selected instance cannot support this policy, pause for an explicit policy decision.

Reconcile imported subjects/external IDs, local mapping count, unmapped users and unchanged ownership counts before cutover. Take an operator-managed encrypted database backup; never commit import exports/checkpoints. Development and production need separate imports into the appropriate instance of this same application; do not assume development users transfer. A short registration/password-change freeze plus final delta import prevents snapshot drift. [Migration overview](https://clerk.com/docs/guides/development/migrating/overview)

## GitHub continuity and credential separation

Enable/test GitHub sign-in in the selected Clerk instance. Keep existing source-integration OAuth client credentials, redirect URI and encrypted `Account` records independently of Clerk social login; do not repoint the source app's callback to Clerk or assume a Clerk login supplies repository authorization. Keep `AUTH_SECRET` available solely for legacy credential encryption until a separately tested re-encryption migration is approved. No token migration to Clerk is proposed.

Clerk can link a social identity by matching verified email, but no direct import of the existing GitHub subject/token is assumed. GitHub-only users first verify their reserved imported email/sign in, then link GitHub through Clerk; test that the resulting subject maps to the original UUID. If GitHub email differs, require authenticated linking to the imported account; do not create/merge legacy owners by email guesses. Changed/inaccessible-email users need operator-assisted recovery with independent identity proof before cutover. These cases block rollout if unresolved. [Account linking](https://clerk.com/docs/guides/configure/auth-strategies/social-connections/account-linking), [GitHub provider](https://clerk.com/docs/guides/configure/auth-strategies/social-connections/github)

Retain `/api/auth/github/start` and `/callback` as source-connection endpoints after cutover, requiring a Clerk-authenticated local user. Remove their anonymous sign-in/user-creation/session-issuance behavior only after approval and tests. Start the flow using authenticated fetch and return an allowlisted GitHub authorization URL for browser navigation; an anchor cannot send the bearer header. Bind one-time state to the local UUID, expiry and HttpOnly state cookie. On callback validate/consume state, fetch the provider profile and enforce the existing numeric GitHub-ID collision checks. The callback may use the state established by the authenticated start rather than rely on a legacy session cookie; it must never issue a sign-in session, create users or switch ownership. Require fresh Clerk authentication for subsequent access. Test cookie mismatch, expiry, replay, wrong provider account and cross-user collision; retaining source callback functionality does not permit anonymous sign-in.

## API and frontend contract

FastAPI's `get_current_user` will verify Clerk session bearer tokens with the supported Python SDK, restrict the issuer to the chosen instance and authorized parties to configured app origins, validate signature/expiry/not-before and intended token type, and resolve `sub` to the local mapping. Configure audience validation if the selected token design uses an audience. Reject absent, malformed, expired, wrong-instance/origin, machine/API-key and unmapped tokens. Use the SDK's key refresh/caching mechanism and fail closed on verification failure; never simply decode JWTs or accept a legacy cookie as fallback after cutover. Short-lived JWT verification has a revocation delay; document measured token lifetime and decide if sensitive operations need an additional active-session check. [Python SDK](https://github.com/clerk/clerk-sdk-python), [Token verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification)

Keep `require_project` and local `User` response shape, including `github_connected` based on source accounts. `/api/auth/me` becomes a Clerk-authenticated application-profile endpoint. Preserve origin protection and stream/upload behavior. Public routes are health and narrowly scoped identity UI/callback routes; no project data is public. Test direct FastAPI access as well as rewritten requests so Next.js cannot mask missing backend enforcement. Unauthenticated APIs return JSON 401, not sign-in HTML.

Introduce an explicit token getter at the API client boundary. Both `request` and `chat` obtain a fresh `useAuth().getToken()` result before sending `Authorization: Bearer …`; multipart preserves automatic boundaries, SSE retains cancellation/backpressure and error handling. Do not cache tokens in local storage, place them in URLs, or send Clerk secret keys to the browser. Disable protected queries while Clerk is loading and clear/abort workspace state on sign-out or account change. Test upload, job polling, streaming and GitHub start paths, not just initial `/me`.

Add `apps/web/proxy.ts` with the current `clerkMiddleware()` and documented matcher (including required Clerk paths); use Next.js 16 naming. Apply server-side protection at the workspace page/data boundary with awaited `auth()`/`auth.protect()` and keep sign-in/up routes reachable. Put ClerkProvider inside `body`, using Suspense/loading boundaries around request-dependent auth content as the selected SDK/rendering mode requires; do not enable Cache Components just for this migration. Show visible sign-in, sign-up and signed-in account/sign-out controls. Use the installed SDK generation's APIs; do not mix Core 2 and Core 3 examples. Re-read local Next.js docs before code changes. [Rendering modes](https://clerk.com/docs/guides/development/rendering-modes), [Protection](https://clerk.com/docs/guides/secure/protect-content)

## File integration strategy (coordinator approval required)

The two design-engine workers retain ownership of their backend/frontend files. This worker owns new Clerk verifier/provisioner/import modules, a new additive Alembic migration, auth tests, `proxy.ts` and new sign-in/up routes. Proposed shared edits are narrowly limited to `models.py` (mapping column), `dependencies.py` (auth adapter), `routes/auth.py` (profile and source-link behavior), `security.py` (session cutover while retaining encryption), configuration/dependency manifests/lockfiles, web root layout/page, API client, workspace auth shell and source-link control. Coordinate current diffs and worker acceptance before changing any shared file; do not rewrite design-engine handlers or UI sections. Keep data-router signatures unchanged. Integrate worker branches later through the coordinator; no merge here.

For UI edits retain the existing Astryx page and sections. Read needed component props; use layout components and tokens, no raw div/span or new unapproved CSS/utility styling. Run `npx astryx doctor --built apps/web/.next` against the eventual build and resolve failures before delivery.

## Execution tasks after approval

### 1. Authenticate and establish a safe setup baseline

- [ ] Record explicit migration approval and agreed shared-file boundaries from the coordinator. Confirm target development/production instance and maintenance policy; do not inspect unrelated applications.
- [ ] Recheck declared/integrated SDK generation without opening environment or claim files. Read local Next.js agent docs and install missing Clerk agent skills using the official `npx skills add clerk/skills` workflow (inspect help/options first), as authorized; do not commit unrelated skill artifacts.
- [ ] If CLI account access is needed, ask the coordinator to have the user run `npx -y clerk@latest auth login` in their own host terminal. Dashboard sign-in is not CLI authentication. Do not request pasted tokens.
- [ ] Only if still no integration, run `npx -y clerk@latest init --app app_3MEbdIf6xt3sJt7mulZI7WMSb6y`; inspect sanitized output without reading generated environment/claim files. If an existing link conflicts, stop, do not relink. If integration exists, configure it in place. Follow current CLI help for doctor and scoped diagnostics without leaking credential content. [Official CLI](https://clerk.com/docs/cli)
- [ ] Commit only reviewed dependency/config/code changes; secrets remain operator-provisioned and ignored. Push the worker branch incrementally.

### 2. Build and prove identity mapping/import

- [ ] First write failing tests for stable UUID/external-ID mapping, concurrent provisioning, email collision, unsupported hashes, 429, timeout reconciliation and resumable import.
- [ ] Add the mapping migration and backend provisioner/import command; keep dry-run read-only. Test Alembic upgrade and rollback on disposable SQLite/Postgres fixtures as applicable.
- [ ] Prove synthetic Argon2 import plus correct/incorrect password sign-in and reserved-email handling in the selected development instance. Prove GitHub-only recovery/linking before declaring import compatible.
- [ ] Commit/push this bounded unit with evidence; do not run real-user imports until target and migration window are confirmed.

### 3. Build and prove end-to-end Clerk authentication

- [ ] First add failing backend tests for invalid/expired/wrong-origin/wrong-instance/token-type rejection, unknown subject, original owner access and other-owner 404. Test all route families including direct API and chat before response streaming.
- [ ] Implement verifier and dependency mapping; adapt `/me`, source-link OAuth and legacy endpoint cutover with Clerk as the sole authentication boundary.
- [ ] Add failing web tests for auth loading, fresh headers on JSON/upload/SSE, account switch cleanup and sign-out; implement provider, proxy, visible controls, protected page and client adapter with the frontend owner's agreement.
- [ ] Replace local-registration fixtures in existing intelligence/foundation tests with trusted test identities; keep real-verifier unit tests independent of mocked route fixtures. Preserve repository ingestion and encryption regressions.
- [ ] Commit/push the verified backend/frontend unit. Do not advertise completion with only frontend protection working.

### 4. Rehearse and execute cutover

- [ ] Run API pytest suite, web tests, production build, type checks available in the repo, Clerk doctor using installed help, and Astryx built-output doctor. Record exact commands/results and any tool limitations.
- [ ] Run the app through Orca and inspect visible sign-in/up, GitHub login, profile and sign-out; exercise password and GitHub-only migrated users, create/read projects, upload, ingestion, SSE chat, expiry and direct unauthenticated API rejection. Redact all credentials from evidence.
- [ ] Rehearse backup/restore and mapping reconciliation. Operator freezes legacy registrations/password changes and sign-in writes, performs final import/delta, validates counts/ownership/source-token decryptability, then atomically deploys Clerk mode frontend/backend. Drain in-flight OAuth and streaming work before switch.
- [ ] In Clerk mode stop local login/register/session issuance, reject old session cookies, revoke/delete legacy session rows and expire the old cookie. Users must sign in again; old sessions are not transferable to Clerk. Clerk sign-out ends Clerk sessions and clears local workspace state. Keep encrypted source credentials intact.
- [ ] Observe redacted auth failures, unmapped identities, ownership denials, source-link errors and import backlog before expanding rollout. Keep snapshots and old auth code/schema for a defined rollback window; delete password hashes/session code only in a separately approved cleanup after recovery is proven.

## Rollback and acceptance gates

The user explicitly removed the proposed compatibility rollback. Recovery now preserves data through additive ownership mappings and independent operator reconciliation; application authentication remains Clerk-only.

Acceptance requires unchanged local ownership IDs, no duplicate imported owners, synthetic and representative password/GitHub flows passing, existing GitHub credentials still decrypting, every protected route rejecting unauthenticated direct requests, cross-owner denial, functional uploads/jobs/chat and visible auth controls, successful build/tests/doctors, and a running app inspected in Orca. Real-instance validation requires authenticated access and operator configuration; unavailable checks remain blockers, not assumed passes.

## Review focus

- Unverified legacy email accidentally imported as verified can enable account takeover: assert reserved status and verified linking/recovery tests in tasks 2–3.
- A failed import response can hide a successful create: test external-ID reconciliation before retry in task 2.
- Removing `AUTH_SECRET` silently strands source tokens: keep encryption regression and source ingestion rehearsal in tasks 3–4.
- A bearer-aware JSON path with cookie-only SSE or source navigation leaves partial auth: test all transport paths in task 3.
- Rollback after Clerk-only signup/password changes can lock users out: rehearse recovery and define the write freeze in task 4.

## Evidence for this documentation phase

Inspected tracked source/dependency declarations, auth/session/user schema, route dependencies, frontend transports, OAuth/encryption implementation and existing test source at baseline commit `594aca4`. Read official CLI and migration docs plus the linked current SDK, user import, account-linking and rendering guidance on 2026-11-17. No application tests/builds or real authentication/migration actions were run for this documentation-only phase; source review is not runtime verification.
