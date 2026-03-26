# Goals Index — langgraph-checkpoint-neo4j

> Central hub for all goals. See individual goal scratchpads for details.

## Goals Tracking

| # | Goal | Status | Priority | Started | Notes |
|---|------|--------|----------|---------|-------|
| 01 | Python Neo4j Checkpointer (v0.0.0) | 🟢 Complete + Released | P0 | 2026-03-26 | v0.0.0 published to PyPI, 59/59 conformance, 87.75% coverage |
| 02 | Python Upstream Parity Testing (v0.0.1) | ⚪ Not Started | P0 | — | Adapt upstream checkpoint-postgres tests for Neo4j; drives v0.0.1 |
| 03 | TypeScript Neo4j Checkpointer (v0.0.1) | ⚪ Not Started | P1 | — | After Python parity is proven, port to TS |
| 04 | PyPI + npm Publishing Pipeline | 🟢 Complete | P2 | 2026-03-26 | Tag-triggered release.yml with OIDC PyPI publish; GitHub Release auto-created |

## Release History

| Package | Version | Tag | Published | Notes |
|---------|---------|-----|-----------|-------|
| `langgraph-checkpoint-neo4j` (Python) | 0.0.0 | `python-v0.0.0` | 2026-03-26 | Initial release — environment/release pipeline validation |

## Recent Activity

- **2026-03-26** — **v0.0.0 published to PyPI** 🎉
  - Tag `python-v0.0.0` pushed → `release.yml` triggered → PyPI publish via OIDC ✅ → GitHub Release created ✅
  - Package: https://pypi.org/project/langgraph-checkpoint-neo4j/0.0.0/
  - Release: https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j/releases/tag/python-v0.0.0
- **2026-03-26** — Merged release chain: `release/python-v0.0.0` → `feature` (PR #1) → `main` (PR #2)
  - Deleted `feature` and `release/python-v0.0.0` remote branches after merge
  - All CI checks green: Python Lint ✅, Python Test ✅, TS Lint ✅, TS Test ✅, CI Success ✅
- **2026-03-26** — Fixed CI failures that blocked PR #1:
  - Added `typescript` as devDependency to `packages/ts/package.json` (TS Lint was failing: `tsc` not available)
  - Changed CI and root `package.json` to use `bun run test` instead of bare `bun test` (Bun test runner exits 1 when no test files found)
  - Regenerated `bun.lock` to include TS workspace + typescript dependency
- **2026-03-26** — CI / release infrastructure stabilized:
  - CI coverage config fixed (`langgraph.checkpoint.neo4j` source target)
  - Python coverage raised to 87.75% with sync integration tests
  - TS bootstrap package added for deterministic CI behavior
  - Lefthook pre-push aligned with fail-fast whole-package checks
  - Release workflow (`release.yml`) + branch protection rulesets created
  - PyPI trusted publisher (OIDC) configured
- **2026-03-26** — Release prep fixes:
  - Migration v4: eagerly registers property keys to silence Neo4j planner warnings on cold starts
  - Async `alist` LIMIT bug fixed (only apply LIMIT when no metadata filter)
  - Ruff per-file-ignores for examples (`T201` print statements)
  - License metadata fixed (SPDX string format)
  - Repo-level LICENSE file created
- **2026-03-26** — Goal 01 implementation complete:
  - `Neo4jSaver` (sync) and `AsyncNeo4jSaver` (async) pass full LangGraph conformance suite (59/59 tests)
  - Package README, examples (`simple_agent.py`, `create_agent_neo4j.py`), `uv build` verified
  - Tasks 01-06 completed in combined implementation push
- **2026-03-26** — Repository created, monorepo skeleton set up, `.rules` written, vendor submodules added

## Next Priorities

1. **Goal 02 — Upstream Parity Testing (v0.0.1)**
   - Adapt upstream `vendor/langgraph-py/libs/checkpoint-postgres/tests/` to Neo4j fixtures
   - Run alongside conformance tests to find subtle semantic differences
   - Gate v0.0.1 release on both conformance + parity suite passing
   - This is the main engineering work for the next milestone

2. **Apply GitHub branch protections in UI**
   - JSON rulesets exist in-repo (`.github/rulesets/main.json`, `.github/rulesets/feature.json`)
   - Need to be confirmed in GitHub Settings → Rulesets
   - Protect `main`: require PR, rebase-only merges, require `CI Success` status check

3. **Goal 03 — TypeScript Checkpointer**
   - After Python parity is proven, port to TS
   - Bootstrap package already exists at `packages/ts/`