# API foundation report

The API uses Clerk as its sole sign-in authority. Protected requests require a verified Clerk bearer token, which maps to the existing application user ID and preserves project ownership. GitHub OAuth is only for connecting a source account after Clerk authentication.

Source-account tokens are encrypted with `SOURCE_TOKEN_ENCRYPTION_KEY`. The forward Alembic migration `c41dd89a0f2a` removes the obsolete password hash column and session table from existing databases. Historical migrations remain unchanged so installations can upgrade through the established migration chain.

The remaining API foundation includes project ownership checks, versioned design reviews, durable ingestion jobs, bounded document extraction, source OAuth state protection and Clerk identity reconciliation. Runtime validation is documented in [VERIFICATION.md](../VERIFICATION.md).
