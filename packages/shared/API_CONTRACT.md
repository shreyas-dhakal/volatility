# Shared implementation contract

All workers read `PROMPT.md`, `plan.md`, `AGENTS.md` first. Shared checkout: edit only assigned paths. Do not commit another worker's work. Root coordinator integrates and runs the complete stack. API prefix `/api`. UUIDs serialized as strings, UTC timestamps ISO strings. Lists return arrays, errors FastAPI `{detail: string}`. Browser uses same-origin Next rewrite `/api/:path*` → `http://127.0.0.1:8000/api/:path*` (configurable `API_URL`). Clerk session tokens are sent as bearer tokens in the `Authorization` header.

## Ownership

Foundation worker owns `apps/api/pyproject.toml`, `uv.lock`, `galvanise/{__init__,config,database,models,security,dependencies,main}.py`, `galvanise/routes/{auth,projects,sources,records}.py`, `galvanise/integrations/`, `galvanise/services/ingestion.py`, `alembic*`, foundation tests, Dockerfiles/Compose, `.env.example`, README foundation sections.

Intelligence worker owns `galvanise/agents/`, `galvanise/graph/`, `galvanise/routes/intelligence.py`, `galvanise/services/knowledge.py`, intelligence tests, `examples/`, `docs/architecture/graphify.md`, `scripts/seed_demo.py`. It may add its own schemas below `agents/` and `graph/`. Never edit foundation models/dependency files; send coordinator a change request.

Web worker owns `apps/web/`, root npm scripts/dependency lock updates if needed, PRODUCT.md/DESIGN.md and UI documentation. It reads real Astryx APIs and generated template. No fake production records or assistant messages. Root demo data only through explicit backend seed.

## Foundation Python exports (must match)

`galvanise.database`: `Base` SQLAlchemy DeclarativeBase, `SessionLocal` synchronous sessionmaker, `get_db()` FastAPI yield dependency.

`galvanise.dependencies`: `get_current_user(request: Request, db: Session = Depends(get_db)) -> User`; `require_project(project_id: str, db: Session, user: User) -> Project` (404 on absent/unowned). Every intelligence route calls this directly or through dependency. No circular imports from main.

`galvanise.config`: `settings` Pydantic Settings instance with `openai_api_key: str`, `openai_model: str` (default gpt-5.5), `database_url`, `clerk_secret_key`, `clerk_jwt_key`, `clerk_issuer`, `clerk_authorized_parties`, `clerk_audience`, `web_url`, `github_client_id`, `github_client_secret`, `github_callback_url`, `max_upload_bytes`. `SOURCE_TOKEN_ENCRYPTION_KEY` encrypts GitHub credentials. Load root `.env` as well as local env. Never print secrets.

`galvanise.models` mapped classes (all IDs `String` with UUID-string Python default):

- `User`: id, email, name, clerk_user_id, created_at.
- `Project`: id, user_id, name, description, system_type (`existing`/`new`), objective, created_at.
- `Conversation`: id, project_id, title, created_at.
- `Message`: id, conversation_id, project_id, role, content, created_at, metadata_json JSON dict default {}.
- `ConnectedSource`: id, project_id, kind, name, status, metadata_json JSON dict, created_at. Token ciphertext in separate account table, never output.
- `SourceDocument`: id, project_id, source_id nullable, name, content (redacted text), media_type, metadata_json JSON dict, created_at.
- `KnowledgeRecord`: id, project_id, kind, title, description, status (`pending`/`approved`/`rejected`), evidence_status (`verified`/`human_confirmed`/`ai_inferred`/`hypothesis`), payload JSON dict, version integer default 1, history JSON list, created_at, updated_at. Use single-table inheritance subclasses named BusinessRequirement, BusinessDecision, ChangeDriver, VolatilityHypothesis, StakeholderQuestion, StakeholderAnswer, ArchitectureCandidate, ArchitectureBoundary, EvidenceReference, TraceabilityLink with polymorphic identity kinds `requirement`, `decision`, `driver`, `volatility`, `question`, `answer`, `architecture`, `boundary`, `evidence`, `traceability` respectively. Base kind may accept all identities. All intelligence persistence uses KnowledgeRecord(kind=...).
- `TechnicalGraph`: id, project_id, source_id nullable, name, nodes_json JSON list, edges_json JSON list, metadata_json JSON dict, created_at. Nodes normalized `{id,label,type,file_path,source_id,metadata}`; edges `{id,source,target,type,metadata}`. Graph can include provenance in metadata.
- `IngestionJob`: id, project_id, kind, status, error nullable, payload JSON dict, created_at, updated_at. Foundation persistent worker queue for uploads/repo indexing; graph import may complete synchronously within strict size limits.

`main.py` registers foundation routers and `from galvanise.routes.intelligence import router` (when available). Tables via Alembic; lifespan may create_all ONLY explicit local/test config, default migrate.

## HTTP foundation

- `GET /api/health` → `{status, ai_configured: bool, github_configured: bool}`
- Clerk is the only sign-in provider. `GET /api/auth/me` returns the authenticated Clerk user profile or 401. The API has no local password or server-session endpoints.
- `GET /api/auth/github/start` redirect GitHub sign-in/connect. callback server only. Secure state and TTL. Least privilege OAuth `read:user user:email` (public repositories; document private-repository GitHub App future limit). Return `WEB_URL` on success. `GET /api/auth/github/repos` → `[{id,full_name,description,private,default_branch}]`.
- `GET/POST /api/projects`, POST `{name,description,system_type,objective}` → Project. `GET /api/projects/{project_id}`.
- `GET/POST /api/projects/{project_id}/conversations`, POST `{title?}` → Conversation.
- `GET /api/projects/{project_id}/conversations/{conversation_id}/messages` → Message[].
- `GET /api/projects/{project_id}/sources` → ConnectedSource[].
- `POST /api/projects/{project_id}/documents` multipart `file` (TXT/MD/PDF/DOCX bounded text extraction) → IngestionJob. `GET /api/projects/{project_id}/documents` → SourceDocument[] (can omit content, separate `GET .../documents/{document_id}`).
- `POST /api/projects/{project_id}/sources/github` `{full_name}` → IngestionJob; validates repo belongs to accessible API list; safe GitHub tree/blob retrieval, no checkout or execution. Source index stores files in SourceDocument and creates TechnicalGraph file nodes ONLY; do not infer dependency edges.
- `GET /api/projects/{project_id}/jobs` → IngestionJob[].
- `GET /api/projects/{project_id}/records?kind=decision` → KnowledgeRecord[] (no kind means all).
- `PATCH /api/projects/{project_id}/records/{record_id}` `{status?,title?,description?,payload?,expected_version: int}` → KnowledgeRecord; append prior snapshot to history and increment version. Explicit review is this HTTP action, never LLM overwrite. 409 stale version. Approved changes require this route.

## HTTP intelligence

- `POST /api/projects/{project_id}/conversations/{conversation_id}/chat` `{content}` → SSE via fetch POST. Events `event: delta` data `{text}`, `event: tool` data `{name,status,result?}`, `event: knowledge` data `{record_ids}`, `event: done` data `{message_id}`, `event: error` data `{message}`. Missing key/model returns actionable HTTP 503 before saving fake assistant. Persist user message; real model response only, persist partial with metadata on failure. Store conversation context across returns. SSE termination must work on disconnect.
- `POST /api/projects/{project_id}/analyse` `{document_ids?: string[]}` → `{records: KnowledgeRecord[]}` structured extraction from selected bounded text/chat. Missing credentials 503.
- `POST /api/projects/{project_id}/graphs/import` multipart `file` → TechnicalGraph summary `{id,name,node_count,edge_count,metadata}`.
- `GET /api/projects/{project_id}/graphs` → summaries. `GET .../graphs/{graph_id}?query=&focus=&limit=80&driver_id=&candidate_id=` → `{id,name,nodes,edges,summary}` with bounded focused graph, real edges, optionally business/traceability/boundary overlays. `GET .../graphs/{graph_id}/nodes/{node_id}` → node detail + real dependencies. `GET .../graphs/{graph_id}/paths?source=&target=` → `{paths: string[][]}` real paths.
- `POST /api/projects/{project_id}/traceability` `{decision_id,graph_id,query?}` → `{records: KnowledgeRecord[]}` retrieval and AI links; validated actual node IDs, AI inferred status. No-key 503.
- `POST /api/projects/{project_id}/questions/{question_id}/answer` `{answer}` → KnowledgeRecord answer plus question payload update/version; human statement evidence only; approved records preserved.
- `POST /api/projects/{project_id}/architectures/generate` `{}` → `{records: KnowledgeRecord[]}` at least conservative + volatility-aware candidates, payload includes boundaries (each with contract/evidence/dependencies/tradeoffs/migration/open_questions).
- `POST /api/projects/{project_id}/evaluate` `{scenario,graph_id?: string,candidate_id?: string,node_ids?: string[]}` → structural calculations only where graph/node mappings exist; `{scenario,mode,current,proposed,assumptions}`. No invented savings. Qualitative comparison when no grounding.
- `POST /api/projects/demo` → Project (explicit seed authenticated user; synthetic label, no fake integrations); sample actual fixtures imported, evidence marked demonstration. Route must precede `/{project_id}`.

## Testing and delivery

Foundation installs all API dependencies up front including FastAPI, SQLAlchemy, alembic, psycopg[binary], pydantic-settings, openai, networkx, httpx, cryptography, python-multipart, pypdf, python-docx; dev pytest, pytest-asyncio, ruff. Python >=3.12 via uv. Isolated SQLite tests allowed; runtime PostgreSQL. Foundation initial migration includes all tables, no enum-specific SQL. Each worker reports exact test/build output and limitations. No live OpenAI or OAuth claim without credentials. Do not log/dump environment credentials.
