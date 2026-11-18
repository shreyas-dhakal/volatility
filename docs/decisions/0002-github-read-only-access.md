# GitHub access in the MVP

Accepted for MVP, 2026-11-17.

Clerk manages GitHub identity linking and provider tokens. Galvanise uses the verified external account of the signed-in owner for public repository reads. Shared development credentials use public GitHub endpoints. Custom credentials in Clerk enable authenticated reads.

GitHub's classic `repo` and `public_repo` OAuth scopes grant repository write access. Galvanise does not request them. GitHub explicitly documents that no scope grants read-only public information access in its [OAuth scope reference](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps).

Private repository ingestion requires a later GitHub App integration with installation-specific `Contents: read` and `Metadata: read` permissions. It is deliberately unavailable in this MVP rather than requesting broad write privileges. The integration interface remains extensible for that implementation and additional information providers.

Source indexing uses GitHub tree/blob APIs, never a checkout, install script, shell command or test execution. File count, blob size and total retrieval limits apply. Source text is redacted before persistence where practical. A file index creates file nodes; it does not pretend to be a dependency extractor. Imported Graphify exports supply structural dependency evidence.
