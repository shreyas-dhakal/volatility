# GitHub access in the MVP

Accepted for MVP, 2026-11-17.

Clerk manages GitHub identity linking and provider tokens. Galvanise uses the verified external account of the signed-in owner for authorized repository reads. Shared development credentials use public GitHub endpoints. Custom credentials in Clerk enable authenticated reads.

GitHub's classic `repo` and `public_repo` OAuth scopes grant repository write access. Galvanise does not request them. GitHub explicitly documents that no scope grants read-only public information access in its [OAuth scope reference](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps).

Private repository ingestion uses the Clerk-brokered GitHub user token. Configure a GitHub App with read-only Contents and Metadata permissions and install it on the repositories to import. Shared development credentials expose only public repositories owned by the linked user.

Source indexing uses GitHub tree/blob APIs, never a checkout, install script, shell command or test execution. File count, blob size and total retrieval limits apply. Source text is redacted before persistence where practical. Opening Code map lets the owner build a structural graph on demand. Graphify parses the saved, redacted files in a temporary directory and Galvanise stores the generated JSON with the project. Existing Graphify exports can also be imported.
