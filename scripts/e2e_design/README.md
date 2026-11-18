# Browser acceptance H

From an integrated checkout on macOS or Linux, use the API's Python environment, the application's installed npm dependencies, Playwright for Node, and Chromium.

```sh
apps/api/.venv/bin/python scripts/e2e_design/run.py
```

The launcher migrates a temporary SQLite database with Alembic, starts FastAPI with its ingestion and design workers, and serves Next on a separate ephemeral loopback port. Playwright registers an account through the API and uses the chat interface to upload a parking brief, inspect a cited tariff, apply a correction, read the diff and previous revision, and reload the saved result. The analysis stages use the shared parking model fixture. The read-only chat reply uses a streaming fixture at the provider boundary.

To reuse existing installations, set `E2E_NODE_MODULES` to the application's node_modules directory, `E2E_PLAYWRIGHT` to a resolvable Playwright package path, and `E2E_BROWSER` to a Chromium-compatible browser executable as needed. The optional `--app-root` argument selects a different integrated Git checkout. Temporary app sources, Next output and the database are removed on exit.
