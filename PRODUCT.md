# Galvanise

Chat-first system architecture workspace for architects and engineering leaders modernising existing systems or planning new ones. Understand why the business changes, connect statements to software evidence, and compare practical architectural boundaries.

The authoritative product brief is PROMPT.md. Users explicitly delegated engineering and design decisions; no additional discovery interview is required for this build.

Primary tasks: create a persistent project, connect read-only sources, discuss business change, review extracted knowledge, answer questions, and compare evidence-backed designs. A repo is optional. Facts, inferences and hypotheses must remain distinguishable.

Platform: responsive desktop-first web application. Operate mode. Neutral Astryx theme and system UI typography. Initial interface: navigation rail, spacious conversation column and collapsible context inspector. No marketing surface, fabricated metrics or prefilled fake conversation.

Engineering assumptions made by the builder: single project owner in MVP; Clerk sign-in plus GitHub OAuth for repository access; public repository read-only OAuth scope initially; PostgreSQL deployment; bounded in-process durable ingestion queue; configurable OpenAI Responses API model.
