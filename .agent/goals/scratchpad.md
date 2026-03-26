# Goals Index — langgraph-checkpoint-neo4j

> Central hub for all goals. See individual goal scratchpads for details.

## Goals Tracking

| # | Goal | Status | Priority | Started | Notes |
|---|------|--------|----------|---------|-------|
| 01 | Python Neo4j Checkpointer (v0.0.1) | 🟢 Complete | P0 | 2026-03-26 | 59/59 conformance tests pass — FULL (5/5 base capabilities) |
| 02 | TypeScript Neo4j Checkpointer (v0.0.1) | ⚪ Not Started | P1 | — | After Python is stable, port to TS |
| 03 | PyPI + npm Publishing Pipeline | ⚪ Not Started | P2 | — | CI/CD for automated releases |

## Recent Activity

- **2026-03-26** — Added local demo coverage for Python package:
  - `packages/python/examples/simple_agent.py` — low-level `StateGraph` persistence demo (sync + async + time travel + delete thread), verified working locally against Neo4j
  - `packages/python/examples/create_agent_neo4j.py` — latest LangChain v1 `create_agent` demo wired to `Neo4jSaver`; prepared but not yet validated end-to-end because no provider API key was available in-session
- **2026-03-26** — Reviewed latest LangChain / LangGraph docs and confirmed:
  - `create_agent` is the recommended modern agent API
  - `create_react_agent` is deprecated
  - `create_agent(..., checkpointer=...)` is the correct high-level persistence path
- **2026-03-26** — Added latest dev dependencies for local modern-agent testing:
  - `langchain==1.2.13`
  - `langgraph==1.1.3`
  - `langchain-openai==1.1.12`
  - `langchain-anthropic==1.4.0`
- **2026-03-26** — Identified release-prep items for future session:
  - run `examples/create_agent_neo4j.py` with a real provider key
  - decide how to handle `print()` in interactive examples vs global `T201` lint rule
  - review final PyPI metadata and publish Python package
  - recommend releasing `0.0.1` (project rule) rather than `0.0.0`
- **2026-03-26** — Goal 01 complete: `Neo4jSaver` (sync) and `AsyncNeo4jSaver` (async) pass full LangGraph conformance suite (59/59 tests). Package README written, `uv build` verified.
- **2026-03-26** — Tasks 02-06 implemented in combined push: `base.py` with Cypher queries/migrations/helpers, full sync+async implementations, `setup()` with migration tracking
- **2026-03-26** — Task 01 complete: project skeleton, namespace packages, conformance test harness, stubs
- **2026-03-26** — Repository created, monorepo skeleton set up, `.rules` reworked, vendor submodules added, Goal 01 started