# Independent design-engine review fixes

The worker branch was fast-forwarded to `origin/main` at `6229ac8` before these
changes. This addresses all three findings in
`docs/reviews/2026-11-17-volatility-engine-independent-review.md`; no frontend or
Clerk files were changed.

## Evidence freshness (P1)

Design artifacts and native intake capture a server-managed `evidence_versions`
map containing directly and transitively referenced KnowledgeRecord evidence.
It stays separate from `input_versions`, which contains only design inputs and
remains compatible with the frontend's existing lookup. Edits, rejections and
missing versioned evidence invalidate consumers and downstream reasoning without
mutating historical approvals. Rejected/foreign/unknown direct or nested evidence
is rejected before design writes. Human payload edits refresh evidence snapshots
while preserving the prior snapshot in review history; status-only approval does
not silently refresh them. In-flight evidence changes return 409 without saves.

## Dependency usability (P2)

Pending same-batch component references remain valid pending proposals. A consuming
component is not current/usable while a dependency is pending, rejected or stale;
validation generation and readiness respect this transitively. Freshness walks
an iterative visited set, including cyclic dependencies, without recursion.
`unusable_dependency` findings explain unavailable inputs. Fully reviewed current
cycles retain the separate `dependency_cycle` finding; readiness still does not
certify architectural correctness.

## Context accounting (P2)

The shared bounded context now counts initial document/message/knowledge/answer
list omissions, per-section title/description/payload/text excerpts, and omitted
characters. It counts only selected records' excerpts, excludes rejected records,
and retains the existing source limits and explicit-selection behavior. Design
budget removals retain separate counters. Counters reach the actual provider
request, persist in proposal metadata, and surface `context_truncated` findings.

## Verification

Regression-first runs reproduced the review's incorrect 200/ready states, missing
snapshot metadata, and missing initial truncation counters before their fixes.
Fourteen new regressions cover direct/upstream/nested evidence edits/rejections,
managed snapshots/history, in-flight changes, unreviewed dependencies, freshness
through approved cycles, exact initial context accounting and persisted warnings.

- `uv run --project apps/api pytest apps/api/tests/test_design_engine.py -q`:
  **53 passed in 4.36s**.
- From `apps/api`, `uv run pytest -q`: **93 passed in 6.58s**.
- `uv run --project apps/api ruff check apps/api/galvanise/services/design.py apps/api/galvanise/services/knowledge.py apps/api/tests/test_design_engine.py`:
  **All checks passed**.
- `git diff --check`: **passed**.
- Checking the existing records route with Ruff still reports its **four existing
  B008 FastAPI Depends-default diagnostics**; this change introduces no new route
  lint findings.

The existing full-suite migration/discriminator compatibility test passes; no
migration is needed. Tests use real routes and persistence with the model provider
mocked. Live OpenAI output, PostgreSQL concurrency and browser UI were not exercised
for these backend fixes. Unversioned source documents/messages and external state
remain outside optimistic version snapshots, although excerpts and omissions are
now reported. Existing historical artifacts without evidence snapshots are treated
as stale when they reference versioned evidence rather than being silently stamped
with current versions.
