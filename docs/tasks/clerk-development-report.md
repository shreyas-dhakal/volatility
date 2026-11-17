# Clerk development integration checkpoint

Development implementation is present; live setup and authentication validation
remain blocked on the user's host CLI login and selected-instance configuration.
This is not a completed Clerk migration or a production-ready sign-in claim.

## Implemented

- Additive unique Clerk-subject mapping preserves local UUIDs and every ownership
  foreign key. New verified users are provisioned once, including concurrent first
  requests; external-ID reconciliation is required before access. Profile changes
  synchronize verified email/name without changing ownership or merging conflicts.
- FastAPI independently verifies bearer session tokens through Clerk's Python
  SDK, checks issuer/origin/time/subject/session, and rejects legacy-cookie
  fallback in Clerk mode. Existing data-router ownership checks are preserved.
- Backend API import tooling defaults to read-only preflight, preserves Argon2
  digests, reserves emails, reconciles timeout/429 retries and persists mappings
  as checkpoints. Development apply requires explicit operator confirmation.
- Source OAuth remains separate from Clerk social sign-in; encrypted GitHub tokens
  and AUTH_SECRET are retained. Clerk-mode source linking starts with an
  authenticated POST and never signs in, creates owners or issues local sessions.
- Next.js 16 proxy, asynchronous server protection, body-level ClerkProvider,
  Suspense sign-in/sign-up forms and visible account controls use Core 3 SDK 7.
  Missing keys deliberately show a setup-needed page without keyless setup.
- JSON, multipart and SSE obtain bearer tokens per request; missing sessions and
  account-change races fail before sending. Account changes unmount previous
  workspace state/streams. Settings/sign-out work before the first project.
- Coordinator's sidebar Settings gear refinement (main 592dfd2) is preserved.

## Verified in this worker

- `APP_ENV=test DATABASE_URL=sqlite:// AUTH_MODE=legacy uv run --project apps/api pytest apps/api/tests -q`: **132 passed**.
- `npm test`: **56 passed** across nine files.
- `npx tsc -p apps/web/tsconfig.json --noEmit`: passes.
- `API_URL=http://127.0.0.1:8091 npm run build`: passes, including TypeScript.
- Ruff checks for the four new backend modules: pass; `git diff --check`: pass.
- Synthetic SQLite migration upgrade/downgrade preserves an existing owner/project.
- `npx astryx doctor --built apps/web`: exit 0, 20 pass, zero failures, three
  warnings covering font proof and the existing source-style rubric.
- Running isolated API **8091**: health 200; unauthenticated profile, project and
  design endpoints 401. The web **3091** rewrite also returns project 401.
- Orca browser inspected the missing-configuration state at localhost:3091 and
  its screenshot; the page renders the centered Astryx login-template frame.

Existing domain fixtures remain in explicit legacy mode; additional Clerk tests
exercise real locally signed JWTs through the installed SDK, with the external
identity service replaced at its network boundary. This proves isolated API
contracts, not a live Clerk session or live import compatibility.

## Pending before completion

1. User runs `npx -y clerk@latest auth login` in their own host terminal and
   confirms completion. No account commands have run since `auth_required`.
2. Because account-free implementation has now installed the integration, skip
   init. Reuse/link only `app_3MEbdIf6xt3sJt7mulZI7WMSb6y` and restore development
   configuration through the supported CLI; never enumerate/select other apps.
3. Provision matching frontend keys and API issuer/authorized origins/server key
   through the host; retain existing source-integration credentials independently.
   No environment/claim files have been read or printed by this worker.
4. Run Clerk doctor and resolve actual findings. Prove synthetic Argon2 import,
   password and GitHub-only sign-in/linking, profile, source access, uploads/jobs,
   streaming, expiry and sign-out against the selected development instance, then
   clean up only the authorized synthetic test users.
5. Repeat the configured production build and inspect actual visible controls in
   Orca. An author self-review has been performed; no helper agent was dispatched.

Real-user imports and production cutover remain separately gated. Main Docker
services on 3002/8000 and their real database have not been modified. The worker
uses its own ports and disposable `/tmp/galvanise-clerk-worker.db`.
