# Design engine API

The design workflow uses the existing project ownership, knowledge records and
optimistic review API. Source code and technical graphs are optional. AI calls
require server-side `OPENAI_API_KEY` and `OPENAI_MODEL`; there is no synthetic
fallback. Generated findings are proposals, not execution verification or scores.

## Workflow

1. `POST /api/projects/{id}/design/use-cases` with `title`, `steps` (nonempty list)
   and `outcome`. Optional fields are `description`, `actor`, `trigger`,
   `preconditions`, `variations`, and project-owned `evidence_ids`. Original
   variations are retained. Records are pending with human-confirmed provenance.
2. `POST /api/projects/{id}/design/generate` with `{"stage":"core"}` discovers
   core cases from nonrejected original cases. Original cases may still be pending.
3. Review via `PATCH /api/projects/{id}/records/{record_id}` using
   `expected_version` and `status: "approved"`. The same API supports edits,
   rejection, history, and 409 responses for outdated versions.
4. Generate `volatility`, `decomposition`, and `validation` separately. Volatility
   requires usable approved cores; decomposition requires usable approved cores
   and volatilities; validation requires usable approved cores, volatilities and
   components. Generation also checks each actual referenced input, so one
   approved record cannot authorize linking a different pending or stale record.
5. `GET /api/projects/{id}/design` returns all five artifact groups, deterministic
   findings and readiness. Readiness means reviewed usable inputs exist, not that
   the architecture is complete or correct. Coverage gaps and cycles can coexist
   with readiness and must be reviewed independently.

Generated artifacts use strict structured output with nonempty links, reasoning,
uncertainty, and contracts. Volatility axes are `over_time`, `across_customer`, or
`both`. Component roles are `client`, `manager`, `engine`, `resource_access`,
`resource`, and `utility`. Generated dependencies accept current-project component
IDs or exact component titles within that generated batch; persisted dependencies
always use IDs. Scenarios must have disjoint changed/unchanged component sets.
All typed links are checked for project ownership and artifact kind before writes.

## Review and freshness

Each generated artifact stores `payload.design_engine`, `input_versions`,
`evidence_versions`, and `context_limits`. These provenance fields are server-managed.
`input_versions` contains only design artifacts, so existing frontend design-input
lookups remain compatible. `evidence_versions` separately captures directly and
transitively referenced KnowledgeRecord evidence; intake also captures this metadata. Existing legacy
volatility and boundary records remain outside this workflow unless they were
created as design-engine artifacts; their existing behavior is preserved.
New discriminator kinds share the existing knowledge table, so no migration is
required. The compatibility test applies the original migration and checks the
current ORM metadata and discriminator loading against that schema.

Generation appends pending revisions with lineage and exact-content deduplication;
it never edits an approved record. Same-batch component dependencies are allocated
atomically, including cyclic proposals and revisions of an approved dependency.
Any invalid result or provider failure saves no part of the generated batch.

Snapshots conservatively include every prior-stage design record's version,
including pending/rejected history. A new prior-stage proposal or any prior-stage
review/edit therefore invalidates downstream snapshots. Earlier approvals remain
intact; regenerate stale stages and review their new proposals. Staleness also
follows linked approved proposals whose own upstream assumptions are stale,
including links changed through human review. Edits, rejection or deletion of
referenced KnowledgeRecord evidence invalidate its consumers and downstream reasoning.
Rejected, unknown or cross-project evidence is blocked during intake, generation
and design payload review, including nested supporting-evidence links. An explicit
human payload edit refreshes its evidence snapshot and retains the old one in
history; status-only approval does not refresh evidence. Older artifacts that lack
snapshots for referenced versioned evidence require review instead of silently
adopting current evidence versions.

Component dependencies can remain pending during proposal creation. A component
with a pending, rejected or stale dependency is not usable for validation; the
overview emits `unusable_dependency`. Freshness follows dependencies with an
iterative visited-set traversal, so cycles do not recurse indefinitely. A cycle
whose members are all reviewed and current still carries a `dependency_cycle`
finding; readiness does not certify architectural correctness.

Snapshots track design records and referenced KnowledgeRecord evidence, not
execution, external system state or changes to unversioned source documents or
messages. A design or supporting-evidence change detected while a provider call is
in flight returns 409 without saving proposals.

The overview adds computed `payload.stale` to design artifacts without changing
stored history. PATCH ignores this computed field on a payload round trip. A stale
validation remains visible with its original snapshot and a `stale_validation`
finding; it does not count toward validation readiness.

## Checks and bounds

Deterministic findings cover uncovered original cases, explicitly unresolved case
mappings, unmapped volatilities, missing contracts, invalid references/payloads,
unknown dependencies, dependency cycles, missing current collaborations/scenarios,
change proposals outside encapsulating components, stale artifacts, and truncation.
Cycle checking uses strongly connected components, avoiding exponential cycle
enumeration. These checks assess record structure and proposed containment only.

Intake fields and lists are bounded by the Pydantic contracts. Generated batches
contain at most 30 records (10 validation records). AI context includes at most
100 typed design inputs; payloads above 10,000 serialized characters are marked as
excerpts and the context is bounded to approximately 90,000 serialized characters.
Typed current reviewed inputs take priority over generic context. The initial
shared context limits are 12 documents, 16 recent messages, 60 knowledge records
and 20 stakeholder answers. Document/message text excerpts are 5,000/2,000
characters; knowledge/answer titles, descriptions and serialized payloads are
bounded at 300/2,000/2,500 characters. `context_limits` reports initial list omissions,
per-section excerpt counts and omitted characters. Explicit document selection is
scoped to that selection. Subsequent removals to fit the design budget have separate
`*_omitted_for_budget` counters. These counters describe successive bounding steps,
not disjoint sets to add together. All counters are passed to the provider, saved
in proposal metadata and exposed through `context_truncated` findings. Overview lists contain the latest 200 records per kind and at
most 500 findings, with top-level `context_limits` reporting omissions. The existing
records endpoint remains available for complete artifact history.

## Verification

Run from `apps/api`:

```sh
uv run pytest -q
uv run ruff check galvanise/agents/design_schemas.py galvanise/services/design.py galvanise/services/knowledge.py galvanise/routes/design.py tests/test_design_engine.py
```

Tests exercise real routes, SQLite persistence, ownership, review history,
prerequisites, schema/reference rejection, atomic batches, version drift, bounded
context, deterministic findings, migrations and approval preservation. Only the
OpenAI provider boundary is mocked; these tests do not verify live model output or
PostgreSQL concurrency behavior.
