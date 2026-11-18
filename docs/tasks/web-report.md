# Web implementation report

The web app uses Clerk for sign-in, session restoration and sign-out. Protected API requests use Clerk bearer tokens, and the API independently verifies each token. There are no local registration or password sign-in screens.

The workspace supports projects, conversations, streaming responses, document uploads, GitHub source connections, review history and architecture exploration. Frontend build and Astryx validation results are recorded in [VERIFICATION.md](../VERIFICATION.md).
