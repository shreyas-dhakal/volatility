# Volatility design engine delivery

The versioned design engine shipped on `main` at `8cca022` on 18 November 2026. It brings volatility-based decomposition, based on Juval Löwy’s approach in *Righting Software*, into the existing project chat. [Implementation diff and all 51 changed files](https://github.com/shreyas-dhakal/volatility/compare/ecc6724...8cca022)

## Use the engine

1. Upload requirements, source code, or a project archive. Choose **Design system** or send “Design this system” in chat.
2. Open **View design** to inspect source coverage, competing assumptions, component responsibilities, contracts, and use-case walkthroughs. Select a citation to read its exact excerpt and source location.
3. Ask a question to discuss the published revision. To change an assumption, send “Correction: …” or select **Apply as correction** on a user message. Inspect the revision diff and open the previous revision to compare.
4. Choose **Plan project** to generate activities from the published architecture. Edit dependencies, effort, skills, and staffing to compare schedules. Add rates to calculate costs.

## Start locally

From the repository root, with the server’s `.env` configured, run:

```sh
./scripts/run-local.sh
```

The launcher applies migrations and starts the API, background workers, and web app. For local password authentication, use `AUTH_MODE=legacy ./scripts/run-local.sh`. Set `OPENAI_API_KEY` on the server. The six design stages use `DESIGN_MODEL` when configured and fall back to `OPENAI_MODEL`. [Setup and test commands](../../README.md#versioned-design-from-chat)

## Verification at delivery

| Check | Result |
| --- | --- |
| Backend | 204 tests passed. The opt-in live OpenAI test passed in a separate run. |
| PostgreSQL | Upgrade, downgrade, re-upgrade, and schema-drift checks passed. All 31 targeted acceptance, persistence, and chat tests passed. |
| Frontend | 56 tests, TypeScript, and the production build passed. Astryx reported zero warnings and zero failures on the built app. |
| Full-stack browser | Chromium uploaded the parking brief, opened its exact tariff excerpt, applied a chat correction, inspected the diff and prior revision, and restored the corrected design after reload. |
| Scheduling | Two independent two-day activities followed by one day of integration took five working days with one qualified person and three with two. The dependency-only critical path was three days for both rosters. |

## Live-model finding

The synthetic parking design passed every citation check. A separate model audit found no source-grounding errors or unsupported volatility claims. It flagged one change-impact mistake in three records. The design predicted that a weekend pricing cap might require editing the exit coordinator. In the brief, Pricing Policy calculates the charge and the coordinator consumes the resulting amount, so the cap should require an edit only to Pricing Policy. [Audit and affected records](versioned-design-live.json)
