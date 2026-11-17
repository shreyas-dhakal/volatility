# Volatility Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Execution uses user-requested Orca Codex worktrees.

**Goal:** Implement a reviewed, traceable use-case-to-system-design engine.
**Architecture:** Extend existing knowledge persistence with typed design artifacts and stage-specific structured AI. Pair these with a guided workspace and deterministic validation checks.
**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, OpenAI Responses, Next.js, React, Astryx.
**Spec:** docs/superpowers/specs/2026-11-17-volatility-engine-design.md

## Global Constraints
Follow the shared API and payload contract in the spec. Preserve existing workflows and reviewed records. Source code is optional. AI proposals require human review. No invented verification or architecture scores. Follow project Astryx rules and run doctor on built output. Commit and push incremental milestones to origin; never push secrets.

## Review Focus
- Cross-project or wrong-kind artifact references must be rejected before writes.
- Approved artifacts must survive repeated AI generation unchanged.
- Updated or rejected inputs must invalidate historical validation/readiness.
- Missing credentials/prerequisites and partial AI failures must produce actionable errors without fake artifacts.
- Original variations, uncovered cases and cyclic component dependencies must remain visible.

### Task 1: Backend engine and invariants (Orca backend worker)
**Files:** create agents/design_schemas.py, services/design.py, routes/design.py, tests/test_design_engine.py under apps/api/galvanise or apps/api/tests respectively; modify models.py/main.py; backend-owned tests and documentation as needed.
**Interfaces:** exact shared endpoints and payloads in spec; reuse records PATCH and save_proposals without weakening validation. Design service owns typed reference checks, stage readiness, deterministic findings and input version tracking.
- [x] Write tests for manual intake/owner checks, stage prerequisites, invalid generated references and preserving approved artifacts; run to see expected failure.
- [x] Implement strict stage schemas, bounded evidence-aware prompts, atomic saves, discriminator models and routes.
- [x] Test coverage findings, cycles, missing contracts and stale validation; implement checks.
- [x] Run complete backend tests and migration compatibility checks; commit and push branch milestone; report SHA, tests and limits.

### Task 2: Guided workspace (Orca frontend worker, independent API contract)
**Files:** create apps/web/components/design-workspace.tsx and tests; modify workspace.tsx, workspace-ui.tsx, lib/types.ts as necessary. Own apps/web only.
**Interfaces:** shared API above; use current request/post helpers and explicit PATCH expected_version reviews. New Design process navigation coexists with Designs.
- [x] Read local Next guides and Astryx component/layout guidance; inspect existing workspace and preserve frame.
- [x] Add meaningful tests for intake, missing configuration/prerequisites, stage actions, review versions and findings.
- [x] Implement use-case intake, five-stage navigation, artifact review/details and reasoning links, coverage/containment findings; retain readable empty/error/loading states.
- [x] Run frontend tests, production build and Astryx built doctor; correct failures; commit and push branch milestone; report SHA and limits.

### Task 3: Integration and review (coordinator after workers settle)
**Files:** integration fixes as needed, README and verification documentation.
- [x] Inspect worker changes and integrate committed milestones into feat/galvanise-mvp without losing baseline.
- [x] Review behavior against every spec section, add missing cross-layer checks, run complete relevant checks and inspect browser workflow.
- [x] Address real failures, document evidence and credential-dependent limits; push integrated tested milestone.
- [x] Obtain independent Orca review of implementation, resolve material issues and push final revision.
