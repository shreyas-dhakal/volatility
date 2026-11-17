# Evidence and architectural recommendations

Accepted for MVP, 2026-11-17.

Galvanise stores architectural knowledge separately from conversation text. Extracted records begin pending and retain evidence status. Approval, rejection and correction are explicit authenticated actions using optimistic versions and retained history. A stakeholder statement is evidence of that statement, not automatic verification of the software's behaviour.

An imported graph establishes only the relationships its exporter describes. Import and dependency edges cannot establish database writes, runtime side effects or business ownership. Dependency paths and structural counts must be calculated from actual edges using NetworkX. Source references and provenance survive normalisation.

Candidate architecture generation compares a conservative option with a volatility-aware option. Internal modules, interfaces, adapters, policy/configuration boundaries and services are all available; deployments are not prescribed by volatility alone. Recommendations remain proposals and include assumptions, operational costs and migration concerns.

When no graph node mapping supports a scenario, evaluation is qualitative. There are no invented confidence percentages, savings figures or maintenance-cost predictions. Structural blast-radius calculations are labelled as potential impact, not proof that every reachable node must change.

Repository and document contents enter prompts as bounded, untrusted evidence. They cannot grant tools permissions, approve changes or override the architect's instructions. Every tool executes within a project whose ownership was checked by the server.
