# Independent final review

Reviewed the current whole project against `PROMPT.md`, `packages/shared/API_CONTRACT.md`, implementation reports, backend routes/services/integrations/agent schemas and stream handling, frontend workflow code, and Docker/startup configuration. No baseline diff exists. This review changed no application code.

## Verdict

**Approved following independent recheck: both reported defects are resolved.** The application is a substantial functional MVP with real persistence, authorization, ingestion, Graphify normalization, OpenAI integration and an Astryx workspace; it is not a static/mock-only implementation. Overall separation of concerns and trust safeguards are appropriate for an MVP. The findings below retain the original failure evidence and describe their resolution. No unresolved material finding remains from this review; credential-backed OpenAI/OAuth and full Docker-image execution remain outside this review's verification scope.

## Findings

### Resolved P1 — Persisted stakeholder answers and human corrections were omitted from AI context

Disposition: independently verified fixed. Shared context now includes bounded descriptions, explicit persistent `stakeholder_answers`, approved-record priority and counts for omitted records. The original isolated reproduction now reports **answer_text_in_context=True**. The new route-to-candidate regression saves an answer, ages out chat history, and asserts that its text reaches the model input.

Location: `apps/api/galvanise/services/knowledge.py:62`; answer persistence in `apps/api/galvanise/routes/intelligence.py:184` (line numbers at review time).

`bounded_context` includes each knowledge record's title, status, evidence status and payload, but omits `description`. `answer()` stores the actual stakeholder answer only in `description`; its payload contains question ID, statement author and uncertainty. Saving an answer through the Questions screen therefore persists the answer without making its text available to subsequent `get_project_context`, extraction, candidate generation or mapping. Description corrections made through the review UI are similarly invisible. A chat-stated answer may temporarily remain in recent messages, but that does not repair persistent context after the bounded history window passes.

Reproduced with a real in-memory SQLAlchemy database: created a human-confirmed answer with description `Supplier approvals are identical across suppliers.`, then serialized `bounded_context`. Checking whether that exact answer appeared returned **False**. No model response or credentials were involved.

Fix: include bounded record descriptions and explicit question-to-answer context in the shared retrieval representation; ensure the record-list tools use the same representation. Add a regression that saves a stakeholder answer via the actual route, then verifies a future model request contains its text even with no recent answer message. Preserve human confirmation as a statement, not independently verified fact.

### Resolved P2 — Title-only deduplication silently discarded changed architecture proposals

Disposition: independently verified fixed. Equivalent substantive content deduplicates; changed content produces a separate pending proposal with `supersedes_id`, revision metadata and predecessor snapshot, preserving approved state. Traceability identity includes graph and decision IDs. The original isolated reproduction now returns a **new ID, updated description and supplier-adapter boundary**, while retaining the approved predecessor unchanged.

Location: `apps/api/galvanise/services/knowledge.py:45-48`.

`save_proposals` treats `(kind, normalized title)` as complete identity and returns the existing record without comparing description/payload. After stakeholders provide new information, regenerating candidates with the same ordinary design names returns the old design and boundaries while the endpoint reports success. This also blocks a changed/rejected proposal from being proposed again under its original name and collides traceability records for same-labeled nodes in different graphs. Preserving approved records is correct; silently discarding a new pending proposal is not required to preserve them.

Reproduced by saving an architecture titled `Conservative design` with description `Old proposal` and empty boundaries, then saving a proposal with the same title, updated description, and a supplier-adapter boundary. Result: **same ID, old description, empty boundaries**. The existing test explicitly expects changed descriptions to be discarded and should be updated to distinguish exact duplicate submissions from changed proposals.

Fix: deduplicate exact equivalent proposals only. For materially changed content create a new pending revision linked to the previous record (or version pending records through an explicit auditable proposal workflow), leaving approved/rejected history intact. Include graph/node/decision identifiers in traceability identity. Add a regeneration regression demonstrating that new evidence produces a reviewable updated design without mutating the approved predecessor.

## Security, integration and validation assessment

No concrete cross-project access bypass, token exposure, fabricated graph-edge calculation, or approved-record mutation by an AI tool was identified. The checked project routes and tools enforce ownership; session/state tokens are hashed, account credentials and queued uploads encrypted, OAuth state browser-bound and single-use, unsafe request origins checked, source code never executed, and imported/model content is labelled untrusted or inferred. Explicit review uses expected-version checks and retained snapshots.

The official AsyncOpenAI Responses SDK pattern is internally consistent: typed `responses.parse(text_format=...)`, strict function schemas with required nullable proposal arguments, streaming output-text deltas, completed function-call items correlated by `call_id`, `previous_response_id` across tool rounds, and completion checks before treating output as complete. Provider failures preserve available partial assistant text. This aligns with the official [structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses) and [Responses migration/function-call guidance](https://developers.openai.com/api/docs/guides/migrate-to-responses?api-mode=responses). This is a source/API-pattern assessment, not credential-backed provider validation.

Docker source paths, dependency installation, migrations-before-API startup, graph/demo fixture copying, web theme copying and build-time internal API rewrites are coherent by inspection. Coordinator reports real PostgreSQL migration/check and credential-free runtime smoke; implementers report 33 backend tests, 13 frontend tests and a production web build passing. This reviewer independently executed the two isolated reproductions above; it did not independently rerun those full suites, build Docker images or claim live OAuth/OpenAI success.

After the fixes, this reviewer independently repeated both isolated reproductions successfully and ran `.venv/bin/python -m pytest -q tests/test_intelligence_api.py -k 'answer_context or exact_dedup or proposals_deduplicate'`: **3 passed, 10 deselected**, exit 0. This verifies the shared-context persistence, exact-content deduplication/revision behavior, rejected reproposals and graph-specific mapping identity covered by those regressions. The implementer reports 35 backend tests passing after the fixes; coordinator owns the final full rerun.

Public-repository-only read-only GitHub access, one API worker, bounded lexical retrieval, synthetic labelled demo evidence, structural rather than measured impact estimates, no OCR, best-effort secret redaction, and deployment rate-limiting/HTTPS/monitoring work are documented MVP limitations. They are not presented here as unexpected defects or demands for fabricated live evidence.
