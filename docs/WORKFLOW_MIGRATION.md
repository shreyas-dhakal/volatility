# Migrate this workflow

Start Galvanise from the repository root. The launcher upgrades PostgreSQL, starts the API and its durable workers, and starts the web app. Set the project’s Clerk configuration in `.env`. Set `OPENAI_API_KEY` and `DESIGN_MODEL` or `OPENAI_MODEL` on the API server to generate scenarios and patches.

```sh
export WORKFLOW_MIGRATION_CONFIG="$HOME/.config/galvanise/migration.json"
./scripts/run-local.sh
```

The migration worker uses the operator’s local Docker engine and Git checkouts. Run the API on that host. The default Compose API container does not receive a Docker socket or host Git checkouts. On Docker Desktop or Colima, keep the inputs on a Docker-shared path. Set `WORKFLOW_MIGRATION_SCRATCH` if the default scratch directory is unsuitable.

## Capture a baseline

1. Open an existing-system project. Index the legacy repository or upload a ZIP from its Git revision. Open **View design** from Chat. The migration action appears inside an observed core use case, an implementation workflow finding or its saved walkthrough.
2. Open **Migrate this workflow**. Search for the entry point, helper, table or destination. Select candidate writes and save them. Search again to find other callers, raw SQL writers, schedulers and triggers. Open citations to inspect the frozen source and nearby transaction boundaries. Graphify suggestions are structural leads. **Execution** labels in replay output indicate directly captured observations.
3. Click **Generate behavior tests**, then edit and save the scenarios. Each proposal contains synthetic fixture data, logical input steps, requested observations and source citations. Match input names and fixture names to the registered adapter. Supply any missing fixture fields before replay.
4. Click **Run legacy baseline**. Every scenario starts with a new container and the same seed data in both legacy runs. Open **Migration activity** and **View result** to compare the runs. Missing observers appear as **Unknown** and unmet setup is recorded as **Not run**.
5. If a generated ID or timestamp is unstable, approve only its concrete field path for the named scenario. Enter a reason. For example:

   ```json
   [
     {
       "scenario": "Normal purchase",
       "path": "/steps/0/response/body/order_id",
       "kind": "id",
       "reason": "The database allocates the order identifier for each equivalent seed."
     }
   ]
   ```

   ID rules preserve a one-to-one relationship across approved fields in the same scenario. Timestamp rules require timezone-aware ISO timestamps on both sides. Other differences must be resolved before approval.
6. Click **Approve immutable baseline**, then **Export legacy replay**. The JSON contains the source revision, adapter fingerprint, scenarios, fixtures, both legacy runs, comparison rules and replay command.

To re-run the pinned legacy source against the exported expected observations:

```sh
cd apps/api
uv run python -m galvanise.migration.replay "$HOME/Downloads/workflow-replay.json" --legacy
```

## Compare or migrate a replacement

Choose a registered local Git target only when starting a replacement action. Add a target convention or a reference from a previous migration. Approve renamed business fields as `legacy` and `replacement` paths within the same table, for example `/database/orders/state` to `/database/orders/payment_state`, with a `reason`. The same mapping applies to pre- and post-invocation captures. Outbound destination, payload and count are compared directly.

**Compare replacement** runs the target revision as it exists. **Generate migration patch** uses the configured OpenAI model with bounded read and edit tools in a private Git worktree, then runs the patch against the same baseline. The coding agent cannot invoke a shell. **Request focused repair** takes one failing scenario and a repair instruction. It runs that scenario first and then the full suite. Each version of the patch and its result remains in activity.

Inspect the earliest observed difference, captured requests, outbound counts and the verified reduced input when available. Record each intentional behavior change by scenario and observed field path, with a reason. A differing capture stays visible after acceptance. Export a patch or the exact comparison replay from its result.

```sh
cd apps/api
uv run python -m galvanise.migration.replay "$HOME/Downloads/workflow-replay.json"
uv run python -m galvanise.migration.replay "$HOME/Downloads/workflow-replay.json" \
  --scenario 'Normal purchase' --smallest
```

The first command replays the full exported replacement. The second replays the stored reduced case when reduction succeeded. Exit status is 0 for a match, 1 for an observed difference, or 2 for an unknown observation or unmet setup.

**Prepare migration PR** appears after an accepted patch has a configured GitHub remote, base branch and working `gh` authentication. Use the confirmation checkbox to authorize a push and draft PR. The branch belongs to that accepted patch. Keep the Git credential in the operator account. Guest containers receive no GitHub or OpenAI credentials.

## Register project replay adapters

The registry is operator-owned JSON and should be readable by the API worker only. Replace the placeholder paths, project ID, reference and image. The project ID appears in API project URLs. Configure only the legacy adapter to start.

```json
{
  "projects": {
    "PROJECT_ID": {
      "legacy": {
        "repo": "/absolute/path/to/legacy",
        "ref": "FULL_LEGACY_COMMIT_SHA",
        "hooks": "/absolute/path/to/legacy_hooks.py",
        "image": "local-legacy-replay:ready",
        "source_prefix": "",
        "fixtures": ["pending_order"],
        "entries": {"purchase": {"method": "POST", "path": "/orders/purchase", "port": 8080}},
        "sqlite": true,
        "redis": true,
        "capture_http": true,
        "replies": {"POST /billing": {"status": 200, "body": {}}}
      },
      "targets": {
        "new-service": {
          "repo": "/absolute/path/to/replacement",
          "ref": "main",
          "hooks": "/absolute/path/to/replacement_hooks.py",
          "image": "local-replacement-replay:ready",
          "entries": {"purchase": {"argv": ["python3", "purchase.py"]}},
          "sqlite": true,
          "redis": true,
          "capture_http": true,
          "edit_scope": ["src/orders/*", "tests/test_orders.py"],
          "repair_scope": ["src/orders/purchase.py"],
          "conventions_path": "src/examples/accepted_migration.py"
        }
      }
    }
  }
}
```

The legacy commit must match the frozen GitHub blob and tree when recorded. For ZIP sources, the runner verifies indexed source content against that commit. Set `source_prefix` if the archive includes a top-level directory absent from the Git tree. The replay export pins the target commit, exact image ID and hook/protocol fingerprint.

Build the runner images before replay with the project’s runtime, installed dependencies, Python 3 and optionally `redis-server`. Build from a secret-free context. Include neither credentials in the image nor production data in fixtures or source. The container starts without network access, uses loopback only, and reads tracked Git source, operator hooks and input data. It has disposable writable scratch space at `/state` and no host credentials or Docker socket. No guest code runs during indexing or on the host.

The hooks file supports these functions:

| Hook | Purpose |
| --- | --- |
| `reset(env)` | Initialize the schema or start a scratch database or queue before seeding. |
| `seed(fixture, values, env)` | Apply one logical fixture to scratch state. Use parameterized queries and explicit fixture handlers. |
| `start(env)` | Start the app on loopback and wait until its local entry point is ready. |
| `invoke(name, entry, data, env)` | Optional operator-owned invocation override, for example for a synthetic auth header. Return a JSON object with `status` and `body`. Otherwise HTTP data is sent as JSON, GET/HEAD values as query parameters, and command inputs on standard input. |
| `observe_db(requests, env)` | Optional observer for other database engines. Return table names mapped to deterministically ordered row lists, or null if unavailable. The built-in SQLite observer uses `GALVANISE_REPLAY_DB`. |
| `drain(env)` | Wait for background processing to reach the point being tested. Return reproducible counts or another stable result. |
| `observe_messages(requests, env)` | Optional observer. Return `{"count": …, "requests": […]}` with destination and payload. The built-in Redis observer captures list pushes, stream adds and publishes on `GALVANISE_REPLAY_REDIS`, including messages that a drain consumes. |
| `observe_jobs(requests, env)` | Return a reproducible pre- and post-invocation worker observation, or null if unavailable. |

Set the app’s outgoing HTTP base URL to `GALVANISE_REPLAY_RECEIVER` inside the hooks. Enable `capture_http` only when the operation’s outgoing destinations are wired there. Configure deterministic receiver replies as needed. Counts are cumulative after each input step. A zero count means the configured observer was active and saw no matching events.

For draft PRs, set `github_remote` to `owner/repository` and `github_base` to its base branch on the target entry. The local target origin must match its HTTPS URL, and `gh auth status --hostname github.com` must succeed under the API operator. Configure a dedicated credential with access to the specific target remote.
