# Task 01 — Project Skeleton & Test Harness

**Status:** 🟢 Complete
**Started:** 2026-03-26
**Completed:** 2026-03-26

---

## Objective

Get `packages/python` to a state where `uv sync` works, `uv run pytest` collects and runs
the conformance test suite, and the project structure is correct for namespace package
coexistence with `langgraph-checkpoint` and `langgraph-checkpoint-conformance`.

## Success Criteria

- [x] `uv sync` installs all dependencies without errors
- [x] `uv run pytest --collect-only` finds `test_conformance_base`
- [x] `uv run pytest` runs the conformance suite (all tests fail with `NotImplementedError` — expected)
- [x] Capability detection correctly identifies 5 base capabilities as `detected: True`
- [x] Extended capabilities (`delete_for_runs`, `copy_thread`, `prune`) correctly `detected: False`
- [x] `ruff check` and `ruff format` pass with zero errors
- [x] Namespace packages work — no collision with `langgraph.checkpoint.conformance`

## What Was Done

### Files Created

| File | Purpose |
|------|---------|
| `src/langgraph/checkpoint/neo4j/__init__.py` | Stub `Neo4jSaver` (sync) — all methods raise `NotImplementedError` |
| `src/langgraph/checkpoint/neo4j/aio.py` | Stub `AsyncNeo4jSaver` (async) — all async methods raise `NotImplementedError` |
| `src/langgraph/checkpoint/neo4j/py.typed` | PEP 561 type marker |
| `tests/__init__.py` | Empty package init for test discovery |
| `tests/conftest.py` | Neo4j driver fixtures (sync + async), env var overrides, auto-cleanup |
| `tests/test_conformance.py` | `@checkpointer_test` registration + `validate()` conformance runner |

### Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Fixed conformance dep version (`>=0.0.1`), enabled namespace package discovery |

### Files Removed

| File | Reason |
|------|--------|
| `src/langgraph/__init__.py` | Was blocking namespace package resolution — upstream uses implicit namespaces |
| `src/langgraph/checkpoint/__init__.py` | Same — must not exist for `langgraph.checkpoint.conformance` to resolve |

### Key Decisions

1. **Implicit namespace packages** — Removed `__init__.py` from `langgraph/` and
   `langgraph/checkpoint/` directories. The upstream `langgraph-checkpoint` and
   `langgraph-checkpoint-conformance` packages also use implicit namespaces (no
   `__init__.py` at those levels). Having regular `__init__.py` files there caused
   `ModuleNotFoundError: No module named 'langgraph.checkpoint.conformance'` because
   Python treated our package as the canonical `langgraph.checkpoint` namespace owner.

2. **setuptools namespace discovery** — Added `namespaces = true` and narrowed
   `include = ["langgraph.checkpoint.neo4j*"]` in `[tool.setuptools.packages.find]`
   to correctly discover our package without interfering with sibling namespace packages.

3. **Conformance version constraint** — Changed `langgraph-checkpoint-conformance>=0.1.0`
   to `>=0.0.1` since only `0.0.1` is published on PyPI.

4. **Neo4j auth flexibility** — `conftest.py` reads `NEO4J_URI`, `NEO4J_USER`,
   `NEO4J_PASSWORD`, `NEO4J_DATABASE` from environment variables with defaults matching
   `docker-compose.yml`. This allows running against an existing Neo4j instance with
   different credentials (e.g. `NEO4J_PASSWORD=immoflow_dev`).

5. **Conformance test structure** — Used `@checkpointer_test` with a `lifespan` that
   verifies Neo4j connectivity, and a factory that cleans up checkpoint nodes before/after
   each capability suite. The `setup()` call is wrapped in `try/except NotImplementedError`
   so the factory doesn't crash before the conformance runner gets to test individual methods.

### Conformance Test Results (Skeleton Stage)

```
Conformance Level: NONE (0/5 base capabilities passing)

BASE CAPABILITIES:
  ❌ put               (17 tests failed — all NotImplementedError)
  ❌ put_writes        (10 tests failed — all NotImplementedError)
  ❌ get_tuple         (10 tests failed — all NotImplementedError)
  ❌ list              (17 tests failed — all NotImplementedError)
  ❌ delete_thread     (5 tests failed — all NotImplementedError)

EXTENDED CAPABILITIES:
  ⊘ delete_for_runs   (not implemented — correctly detected)
  ⊘ copy_thread       (not implemented — correctly detected)
  ⊘ prune             (not implemented — correctly detected)
```

This is the expected result. All 59 conformance tests fail with `NotImplementedError`,
confirming that:
- The test harness works end-to-end
- Capability detection correctly identifies our overridden methods
- The conformance framework can instantiate and interact with our checkpointer

## Notes for Next Tasks

- **Task 02 (Schema & Setup):** Implement `setup()` on both savers. Will need to create
  Neo4j indexes/constraints and migration tracking. Reference the Cypher queries planned
  in the goal scratchpad (AD-01).

- **Task 03 (put + get_tuple):** This is the bulk of the work. The `_dump_blobs` /
  `_load_blobs` / `_dump_writes` / `_load_writes` helper pattern from the Postgres
  `BasePostgresSaver` should be adapted for Neo4j Cypher queries.

- **Running tests:** Use `NEO4J_PASSWORD=<password> uv run pytest` if the local Neo4j
  instance uses non-default credentials.