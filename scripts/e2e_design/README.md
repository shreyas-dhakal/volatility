# Browser acceptance H

From an integrated checkout on macOS or Linux, use the API's Python environment,
the application's installed npm dependencies, Playwright for Node, Chromium, and
a Playwright storage-state file for a user signed in to the configured Clerk
instance.

Export these values before running the launcher:

```sh
export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...
export CLERK_SECRET_KEY=...
export CLERK_ISSUER=...
export CLERK_E2E_STORAGE_STATE=/path/to/clerk-storage-state.json
apps/api/.venv/bin/python scripts/e2e_design/run.py
```

The launcher migrates a temporary SQLite database and starts FastAPI and Next
on loopback ports. Playwright opens the authenticated Clerk workspace, creates a
project through the UI, uploads a parking brief, inspects tariff evidence,
answers the formula question, compares revisions, checks saved IDs after reload,
and exercises chat correction. Analysis stages use deterministic fixtures; chat
uses a streaming fixture at the provider boundary. The Clerk storage state and
keys are read from the environment and never copied into the temporary app.

Set `E2E_NODE_MODULES`, `E2E_PLAYWRIGHT`, and `E2E_BROWSER` to reuse existing
installations. `--app-root` selects another integrated checkout. Temporary app
sources, Next output and the database are removed on exit.
