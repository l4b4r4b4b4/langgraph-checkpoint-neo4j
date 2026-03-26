# Goal 02 — Python Upstream Parity Testing (v0.0.1)

**Status:** ⚪ Not Started
**Started:** —
**Completed:** —
**Priority:** P0 — Next milestone after v0.0.0 release
**Depends on:** Goal 01 (🟢 Complete + Released)

---

## Objective

Adapt the upstream LangGraph checkpoint-postgres test suite to run against
the Neo4j checkpointer. Use these tests to discover and fix any subtle
semantic differences between our implementation and the reference Postgres
checkpointer. Gate the v0.0.1 release on both the official conformance suite
**and** the adapted parity test suite passing.

## Why This Matters

The official conformance suite (59 tests, 5 base capabilities) validates the
**contract** — that our checkpointer implements the required interface methods
correctly. But the upstream Postgres test suite exercises **real-world usage
patterns** that the conformance suite doesn't cover:

- Complex multi-step graph executions with branching
- Concurrent writes and read-after-write consistency
- Edge cases in metadata filtering and checkpoint ordering
- Interaction with LangGraph's internal state management
- Pending sends / task channel handling in realistic scenarios

Passing parity tests gives us **high confidence** that
`langgraph-checkpoint-neo4j` is truly a drop-in replacement, not just a
contract-conformant approximation.

## Success Criteria

- [ ] Upstream checkpoint-postgres tests adapted to use Neo4j fixtures
- [ ] All adapted tests pass against `Neo4jSaver` and `AsyncNeo4jSaver`
- [ ] Any semantic differences discovered are documented and fixed
- [ ] Parity test suite runs in CI alongside conformance tests
- [ ] Coverage remains ≥ 72% (currently 87.75%)
- [ ] v0.0.1 released to PyPI with parity tests passing

## Reference Files

### Upstream test files to adapt

Located in `vendor/langgraph-py/libs/checkpoint-postgres/tests/`:

| File | Purpose |
|------|---------|
| `test_sync.py` | Sync PostgresSaver integration tests |
| `test_async.py` | Async AsyncPostgresSaver integration tests |
| `test_store.py` | Store operations (if applicable) |
| `conftest.py` | Postgres fixtures, connection setup |

**Important:** These files need to be studied in detail at the start of this
goal. The exact file names and test structure may differ from what's listed
above — verify against the actual vendor submodule content.

### Our existing test files

| File | Purpose |
|------|---------|
| `packages/python/tests/conftest.py` | Neo4j driver fixtures (sync + async) |
| `packages/python/tests/test_conformance.py` | Official conformance wrapper |
| `packages/python/tests/test_sync_saver.py` | Sync integration smoke tests |

## Preliminary Task Breakdown

> These tasks are **preliminary** — they should be refined during Step 1
> (Gather Context & Research) after studying the upstream test files.

### Task 01: Study Upstream Tests
- Read all test files in `vendor/langgraph-py/libs/checkpoint-postgres/tests/`
- Catalogue every test case and what it exercises
- Identify which tests are Postgres-specific vs. checkpointer-generic
- Identify which tests overlap with the conformance suite
- Produce a mapping table: upstream test → adaptation plan

### Task 02: Create Neo4j Parity Fixtures
- Adapt upstream `conftest.py` to use Neo4j driver/session
- Ensure test isolation (clean up between tests)
- Handle any Postgres-specific fixture patterns (connection pooling, etc.)

### Task 03: Adapt Sync Tests
- Port upstream sync tests to use `Neo4jSaver`
- Place in `packages/python/tests/parity/` or similar
- Run and fix failures iteratively

### Task 04: Adapt Async Tests
- Port upstream async tests to use `AsyncNeo4jSaver`
- Run and fix failures iteratively

### Task 05: CI Integration + Release
- Add parity tests to CI pipeline
- Verify coverage threshold still met
- Bump version to `0.0.1` in `pyproject.toml`
- Tag `python-v0.0.1` and release

## Architecture Notes

### Test placement

Parity tests should live in a dedicated directory to keep them distinct from
our own integration tests and the conformance wrapper:

```
packages/python/tests/
├── conftest.py              # shared Neo4j fixtures
├── test_conformance.py      # official LangGraph conformance
├── test_sync_saver.py       # our own sync smoke tests
└── parity/                  # adapted upstream tests
    ├── __init__.py
    ├── conftest.py           # parity-specific fixtures (if needed)
    ├── test_sync_parity.py   # adapted from upstream test_sync.py
    └── test_async_parity.py  # adapted from upstream test_async.py
```

### Adaptation strategy

1. **Copy, don't import** — copy test functions from upstream and modify
   fixtures. Don't try to import upstream test modules directly (they have
   Postgres-specific imports and fixtures).

2. **Preserve test names** — keep original test function names where possible
   so we can easily cross-reference with upstream.

3. **Mark Postgres-specific tests** — some tests may be inherently
   Postgres-specific (e.g., testing SQL-level features). Skip these with
   `@pytest.mark.skip(reason="Postgres-specific: ...")` rather than deleting
   them, so we can audit completeness.

4. **Document differences** — if our checkpointer intentionally differs from
   Postgres behavior, document why in the test file and in this scratchpad.

## Known Potential Differences

These are areas where Neo4j's behavior may legitimately differ from Postgres
and could cause test failures:

1. **JSON containment queries** — Postgres has `@>` for JSONB containment;
   we post-filter metadata in Python. This should be semantically equivalent
   but may have edge cases with nested metadata.

2. **Ordering guarantees** — checkpoint_id ordering is lexicographic in our
   Cypher queries. Verify this matches Postgres ordering.

3. **Transaction isolation** — Neo4j auto-commit sessions vs. Postgres
   explicit transactions. Concurrent access patterns may behave differently.

4. **Type coercion** — Neo4j is stricter about types (int vs string).
   We already handle version-as-string, but there may be other cases.

5. **Blob handling** — Neo4j may return `bytearray` where Postgres returns
   `bytes`. We handle this in `_load_blobs` / `_load_writes` but there may
   be edge cases.

---

## Session Log

### 2026-03-26 — Priority clarification after TS parallel progress 🟢

#### What happened
- Python parity work has **not started yet**
- In parallel, substantial TypeScript implementation work was completed under Goal 03
- The TS checkpointer now has a first real implementation and passes **699 / 714**
  upstream validation tests
- This was useful progress, but it does **not** change the next release-driving
  priority for Python

#### Priority decision
**Goal 02 remains the next highest-priority engineering task.**

The Python package is already released as `0.0.0`, and the next milestone
(`v0.0.1`) should still be driven by **upstream parity testing for the Python
implementation**.

That means the next session should treat the following as the primary work:
1. study upstream Python checkpoint-postgres tests in the vendor submodule
2. adapt them to Neo4j fixtures
3. run them alongside conformance tests
4. fix any semantic gaps they reveal
5. only then prepare `v0.0.1`

#### Why this is still the right priority
The Python package is already published and usable, but conformance alone is not
the same as high-confidence parity with the upstream Postgres checkpointer.

The TypeScript work, while promising, is still:
- unpublished
- not yet CI/release-gating
- not yet fully validation-clean

So TS should continue only as **parallel / secondary work** unless priorities
change explicitly.

#### Related progress outside this goal
Goal 03 now documents the TypeScript implementation status:
- `Neo4jSaver` implemented
- Cypher/migrations extracted
- validation harness wired
- **699 / 714** upstream validation tests passing
- remaining failures are mostly Bun test-runner compatibility issues plus a few
  saver edge cases

#### Immediate next step for Goal 02
Start **Task 01: Study Upstream Tests** and turn the preliminary task list in
this file into a concrete file-by-file adaptation plan.
