# Goal 03 — TypeScript Neo4j Checkpointer (v0.0.1)

**Status:** 🟡 In Progress — published v0.0.0, migration idempotency fix needed
**Started:** 2026-03-26
**Completed:** —
**Priority:** P1 — Now co-primary with Python (both need migration fix)
**Depends on:** Goal 01 (🟢 Complete + Released)
**Related:** Goal 02 (Python parity testing remains the primary next milestone)

---

## Objective

Implement a Neo4j-backed checkpointer for LangGraph.js / TypeScript that is a
drop-in replacement for the official Postgres checkpointer, compatible with Bun
workspaces and validated against the upstream
`@langchain/langgraph-checkpoint-validation` suite.

The initial target is **functional parity with the TypeScript Postgres
checkpointer's core checkpoint API**:

- `getTuple`
- `list`
- `put`
- `putWrites`
- `deleteThread`

This goal is **not yet** the top release priority. The Python package is
already published as `0.0.0`; the next immediate release-driving work remains
**Goal 02: Python upstream parity testing**. Still, meaningful TypeScript
implementation progress has already been made and is documented below so the
next session can continue cleanly.

## Why This Matters

A TypeScript implementation would make the repo a true polyglot Neo4j
checkpointer project:

- Python users get `langgraph-checkpoint-neo4j`
- TypeScript / Bun users get `@luke_skywalker88/langgraph-checkpoint-neo4j`

This is especially useful for teams already running Neo4j in agent systems and
wanting a single persistence backend across Python and JS runtimes.

## Current State Summary

### Implemented already

A substantial first-pass TypeScript implementation now exists under
`packages/ts/`:

- `packages/ts/src/index.ts`
  - `Neo4jSaver` class implemented
  - extends `BaseCheckpointSaver<number>`
  - implements all 5 required abstract methods
  - includes:
    - `fromConnString()`
    - `close()`
    - `setup()`
    - `getTuple()`
    - `list()`
    - `put()`
    - `putWrites()`
    - `deleteThread()`
    - helper methods for blob / write serialization and tuple reconstruction
- `packages/ts/src/cypher.ts`
  - Cypher constants and migrations extracted into their own module
  - mirrors the proven Python Cypher implementation
- `packages/ts/src/tests/validate.test.ts`
  - Bun smoke/regression coverage
- `packages/ts/tests/validation.vitest.ts`
  - upstream validation suite wired to
    `@langchain/langgraph-checkpoint-validation`
- `packages/ts/package.json`
  - real package metadata and dependencies added
- `packages/ts/tsconfig.json`
  - updated for Bun runtime typing

### Validation status

The TypeScript test strategy is now explicitly split across two runners:

- **Bun smoke/regression tests** (fast, Bun-native): `packages/ts/src/tests/validate.test.ts`
- **Upstream validation suite under Vitest/Node** (framework-compatible): `packages/ts/tests/validation.vitest.ts`

**Current status:**
- **Bun smoke tests:** `6 / 6` passing
- **Upstream validation (Vitest/Node):** `714 / 714` passing (**100%**)

After targeted saver fixes and runner split, functional behavior and validation
coverage are both green.

## Success Criteria

### Minimum implementation criteria
- [x] `Neo4jSaver` extends `BaseCheckpointSaver`
- [x] All 5 required abstract methods implemented
- [x] Cypher migrations and query constants extracted to dedicated module
- [x] Bun / TS package metadata and dependencies added
- [x] Validation test wired up

### Functional validation criteria
- [x] TypeScript implementation runs against upstream validation suite
- [ ] All validation tests pass cleanly
- [ ] TS implementation integrated into CI in a release-ready way
- [ ] Clear runtime support statement documented (`bun` + `neo4j-driver`)
- [ ] Release plan defined for npm publishing

### Release criteria
- [ ] Package is no longer marked `private`
- [ ] Versioning and npm publish workflow decided
- [ ] Published to npm as `@luke_skywalker88/langgraph-checkpoint-neo4j`

## Files and Structure

Current TypeScript package structure:

```text
packages/ts/
├── package.json
├── tsconfig.json
└── src/
    ├── cypher.ts
    ├── index.ts
    └── tests/
        └── validate.test.ts
```

## Package Setup

### Current runtime dependencies
- `neo4j-driver`
- `@langchain/langgraph-checkpoint`

### Current peer dependency
- `@langchain/core`

### Current dev dependencies
- `typescript`
- `bun-types`
- `@langchain/langgraph-checkpoint-validation`
- `@langchain/core`

### Current package state
- version: `0.0.0`
- `private: false` (release-prepared for npm publish)
- build output configured to `dist/`
- exports configured for ESM + types

## Architecture Decisions

### AD-01: Reuse the Python Cypher model
The TypeScript implementation mirrors the Python implementation's data model and
Cypher statements instead of inventing a separate TS-specific schema.

That means:
- `Checkpoint` nodes
- `CheckpointBlob` nodes
- `CheckpointWrite` nodes
- `CheckpointMigration` nodes

This keeps cross-language behavior aligned and reduces schema drift.

### AD-02: Use official `neo4j-driver`
The TS implementation uses the official `neo4j-driver` package.

Rationale:
- there is no known Bun-native high-performance Neo4j driver comparable to
  Bun's Postgres or SQLite integrations
- the official driver is the only realistic production option
- it is pure JS and works under Bun's Node compatibility layer

### AD-03: Use integer channel versions in TypeScript
The current TS implementation extends `BaseCheckpointSaver<number>` rather than
`BaseCheckpointSaver<string>`.

Rationale:
- this aligns with the upstream TS Postgres implementation
- it matches the validation suite's generic expectations more naturally
- it reduces friction in first-pass compatibility

Note: this differs from the Python implementation, which uses string version
identifiers. This difference should be kept in mind if cross-language parity is
ever required at the serialized storage level.

### AD-04: Keep validation harness inside package source for now
A first validation test was added under `src/tests/validate.test.ts`.

This is acceptable for now to accelerate iteration, but test placement may need
cleanup later depending on build / publish strategy.

## Reference Files

### Upstream TypeScript references
These were studied during implementation:

- `vendor/langgraph-js/libs/checkpoint/src/base.ts`
- `vendor/langgraph-js/libs/checkpoint/src/serde/base.ts`
- `vendor/langgraph-js/libs/checkpoint/src/serde/jsonplus.ts`
- `vendor/langgraph-js/libs/checkpoint-postgres/src/index.ts`
- `vendor/langgraph-js/libs/checkpoint-postgres/src/sql.ts`
- `vendor/langgraph-js/libs/checkpoint-postgres/src/migrations.ts`
- `vendor/langgraph-js/libs/checkpoint-validation/src/types.ts`
- `vendor/langgraph-js/libs/checkpoint-validation/src/spec/put.ts`
- `vendor/langgraph-js/libs/checkpoint-validation/src/spec/get_tuple.ts`
- `vendor/langgraph-js/libs/checkpoint-validation/src/spec/list.ts`
- `vendor/langgraph-js/libs/checkpoint-validation/src/spec/put_writes.ts`
- `vendor/langgraph-js/libs/checkpoint-validation/src/spec/delete_thread.ts`

### Internal references
- `packages/python/src/langgraph/checkpoint/neo4j/base.py`
- `packages/python/src/langgraph/checkpoint/neo4j/__init__.py`

The TS implementation intentionally reuses the Python Cypher and migration logic
where possible.

## Validation Findings

### What passed
The majority of the suite passed immediately after first implementation:
- `put()` happy-path behavior
- metadata roundtrip
- checkpoint retrieval for many cases
- list behavior for most combinations
- delete thread behavior
- write storage behavior for many cases

### Current runner compatibility and coverage status

There are currently **no known saver-behavior failures** in the TypeScript
validation matrix.

#### Bun runner status
- Bun remains the primary local runtime for package development.
- Bun executes a focused smoke/regression suite (`6 / 6` passing).

#### Upstream parity status
- The official `@langchain/langgraph-checkpoint-validation` suite now runs
  under Vitest/Node and passes fully (`714 / 714`).
- This avoids Bun assertion API mismatches (`expect.soft`, async-function
  `rejects` style) while preserving full upstream conformance coverage.

#### Resolved saver behavior items
- ✅ Pending sends migration alignment with upstream TS Postgres (`checkpoint.v < 4` gate)
- ✅ `getTuple()` malformed `thread_id` handling (`undefined` instead of throw)

## Known Risks / Open Questions

### 1. Bun vs validation-suite framework assumptions
The upstream validation package appears to assume assertion behavior closer to
Vitest than Bun in a few places.

This creates ambiguity:
- Are failing tests implementation bugs?
- Or are they framework-portability issues?

This should be isolated carefully before changing saver logic.

### 2. Neo4j driver behavior under Bun
No known Bun-native high-performance Neo4j client exists.
The current implementation depends on the official JS driver.

This is likely the correct choice, but should be documented clearly:
- Bun support is practical, not necessarily officially guaranteed by Neo4j
- the implementation is running through the Node compatibility layer

### 3. Test file placement
The validation test currently lives under `src/tests/`.
We may want later to move tests to:
- `packages/ts/tests/`
or similar,
depending on how we want the build pipeline to treat them.

### 4. CI policy for TS tests
The repo currently has a TS bootstrap setup and a placeholder test path.
Once we want TS work to become release-driving, CI needs a deliberate policy:
- should TS validation tests run on every PR?
- only when `packages/ts/**` changes?
- only after Goal 02 is complete?

## Proposed Next Steps

### 🟢 DONE — Migration idempotency fix (BOTH languages)

Both Python and TypeScript `setup()` methods had a **migration recording bug**
that caused failures when tests ran against a shared Neo4j instance or when
`setup()` was called concurrently.

**Fixed in session 2026-03-26 (second session).** See session log below.

#### Root cause (same in both languages)

`setup()` used `CREATE (m:CheckpointMigration {v: $v})` to record each
completed migration. This failed with a uniqueness constraint violation if the
migration node already existed (e.g. from a prior test run that cleaned
checkpoint data but left migration nodes, or from concurrent `setup()` calls).

#### Fix applied

1. Changed migration recording from `CREATE` to `MERGE` in all three files:
   - `packages/python/src/langgraph/checkpoint/neo4j/__init__.py` (sync `setup()`)
   - `packages/python/src/langgraph/checkpoint/neo4j/aio.py` (async `setup()`)
   - `packages/ts/src/index.ts` (TS `setup()`)

2. Fixed Python `put_writes()` UPSERT/INSERT logic (both sync and async):
   - **Before (wrong):** `channel in TASKS` — substring check on `"__pregel_tasks"`
   - **After (correct):** `channel in WRITES_IDX_MAP` — dict lookup matching upstream Postgres
   - This also fixed the inverted logic: WRITES_IDX_MAP channels (ERROR, SCHEDULED,
     INTERRUPT, RESUME) now correctly get UPSERT; everything else gets INSERT.

3. **Python sync `get_tuple()` returning `None`** — resolved by the above fixes.
   Root cause was the migration `CREATE` failures causing `setup()` to not
   complete reliably, combined with the `put_writes` logic bug. After both
   fixes, all 4 Python tests pass consistently.

#### Verification results (fresh DB)

- Python: **4/4** pass (conformance + 3 sync tests) ✅
- TS Bun smoke: **6/6** pass ✅
- TS Vitest validation: **714/714** pass ✅
- Cross-language shared-DB: Python → TS without DB reset ✅

### Short-term (after migration fix)
1. Keep the split testing strategy stable:
   - `bun run test:bun` for Bun smoke/regression checks
   - Vitest/Node for upstream conformance (`714 / 714`)
2. Keep CI/release guardrails intact:
   - Bun smoke tests must stay green
   - Vitest upstream validation must stay green
   - TS publish flow must enforce package name/version/private gates
3. Continue parity work only when new upstream changes introduce real behavior deltas
4. Keep documentation synchronized across:
   - `packages/ts/README.md`
   - root `README.md`
   - this goal scratchpad

### Medium-term
5. Clean up package exports and build boundaries
6. Prepare v0.0.1 release with migration fix
7. Cross-language coexistence testing (Python + TS on same Neo4j)

### Priority guidance
Both Python and TS now need the same migration idempotency fix.
Python parity testing (Goal 02) remains important for v0.0.1, but the
migration fix is a blocker for both languages and should be done first.

## Session Log

### 2026-03-26 (session 2) — Bug fixes, put_writes correction, TS example 🟢

#### What was done
- **Bug 1 fixed:** Changed `CREATE` → `MERGE` in migration recording for all
  three `setup()` methods (Python sync, Python async, TypeScript)
- **Bug 2 found and fixed:** Python `put_writes()` had incorrect UPSERT/INSERT
  logic — `channel in TASKS` (substring check on a string) instead of
  `channel in WRITES_IDX_MAP` (dict lookup matching upstream Postgres). Also
  fixed the inverted logic: WRITES_IDX_MAP channels should UPSERT, others INSERT.
  Both sync and async variants fixed.
- **Bug 3 resolved:** Python sync `get_tuple()` returning `None` was caused by
  the migration and put_writes bugs above. After fixes, all tests pass consistently.
- **Multi-turn chat example (TS):** Created `packages/ts/examples/multi-turn-chat.ts`
  demonstrating: multi-turn conversation, state retrieval, checkpoint history,
  time travel, pending writes, persistence proof (close→reopen→verify), cleanup.
  Uses `emptyCheckpoint()` and `uuid6()` from upstream SDK for correct time-sorted IDs.
- **Verified Python example:** `packages/python/examples/simple_agent.py` runs
  correctly end-to-end (sync demo, async demo, persistence proof).
- All tests verified on fresh DB + cross-language shared-DB scenario.

#### Concrete outcomes
- 3 files edited for migration fix (1-line change each)
- 2 files edited for put_writes fix (`__init__.py` and `aio.py`)
- `WRITES_IDX_MAP` import added to both Python modules
- `packages/ts/examples/multi-turn-chat.ts` created (~420 lines)
- Feature branch: `fix/migration-idempotency-and-put-writes`
- Test results: Python 4/4, TS Bun 6/6, TS Vitest 714/714

#### Files changed
- `packages/python/src/langgraph/checkpoint/neo4j/__init__.py` — MERGE fix + put_writes fix + import
- `packages/python/src/langgraph/checkpoint/neo4j/aio.py` — MERGE fix + put_writes fix + import
- `packages/ts/src/index.ts` — MERGE fix
- `packages/ts/examples/multi-turn-chat.ts` — new file

---

### 2026-03-26 (session 1) — Initial TypeScript implementation session 🟢

#### What was done
- Researched Bun + Neo4j ecosystem
  - conclusion: no Bun-native high-performance Neo4j driver exists
  - official `neo4j-driver` is the practical choice
- Studied upstream LangGraphJS checkpoint interface and validation suite
- Studied upstream TS Postgres checkpointer implementation
- Implemented first real TypeScript `Neo4jSaver`
- Added Cypher constants and migration system
- Added validation test harness
- Verified typecheck and build pass
- Ran validation suite against local Neo4j

#### Concrete outcomes
- `packages/ts/src/index.ts` implemented
- `packages/ts/src/cypher.ts` created
- `packages/ts/src/tests/validate.test.ts` now serves as Bun-native smoke/regression coverage
- `packages/ts/tests/validation.vitest.ts` added for upstream validation under Vitest/Node
- TS package has full dependency/build/test metadata plus publish-ready metadata
- Validation result (initial): **699 / 714 passing**
- Validation result (Bun smoke suite): **6 / 6 passing**
- Validation result (upstream validation via Vitest/Node): **714 / 714 passing**
- CI/release workflows updated for dual-runner TS testing and Neo4j image tag `neo4j:2026-community`
- TS release hardening completed:
  - `prepublishOnly` guard pipeline
  - release workflow publishability checks (name/version/private)
  - package-level publish checklist documentation
  - root README TypeScript release quickstart documentation

#### Important conclusions
- The TS implementation is no longer speculative — it is functionally validated and operationally hardened.
- Upstream parity validation is now fully green via Vitest/Node, while Bun keeps fast local smoke confidence.
- Release-readiness is now materially improved with workflow/package guardrails and explicit documentation.
- Python parity remains the release-driving priority for `v0.0.1`, with TS now in a stable parallel track.
- **v0.0.0 published** to npm as `@luke_skywalker88/langgraph-checkpoint-neo4j`
- **Migration idempotency bug** discovered affecting both Python and TS when
  running against a shared/reused Neo4j instance — fix is documented above.

---
## Handoff Notes

### Status after session 2

All critical bugs are fixed and verified. The codebase is on feature branch
`fix/migration-idempotency-and-put-writes` — needs PR + merge to main.

#### What was completed
- [x] Migration `CREATE` → `MERGE` fix (all 3 files)
- [x] Python `put_writes` UPSERT/INSERT logic fix (both sync + async)
- [x] Python sync `get_tuple()` returning `None` — resolved by above fixes
- [x] Verified on fresh DB: Python 4/4, TS Bun 6/6, TS Vitest 714/714
- [x] Cross-language shared-DB coexistence verified
- [x] TS multi-turn chat example created and tested
- [x] Python example (`simple_agent.py`) verified end-to-end

#### Remaining for next session
1. **PR + merge** — create PR from `fix/migration-idempotency-and-put-writes` → `main`
2. **Tag releases** — `ts-v0.0.1` and `python-v0.0.1` after merge
3. **Bump `.bun-version`** from `1.3.10` to `1.3.11` (local Bun is 1.3.11)
4. **Optional:** Add `create_agent` example for TS (needs `@langchain/langgraph` as
   dev dependency; currently the TS example uses raw checkpoint API which is fine)
5. **Optional:** CHANGELOG.md entries for both packages

### Useful commands

```text
# Fresh Neo4j (clean volumes)
docker compose down -v && docker compose up -d neo4j

# Wait until browser endpoint responds
curl http://localhost:7373

# All tests
NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password bun run test

# Python tests
NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password bun run test:python

# TS Bun smoke tests
NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password bun run test:ts

# TS upstream validation (Vitest/Node)
NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password bun run test:ts:validation

# TS both layers
NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password bun run test:ts:all

# Run examples
cd packages/python && NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password uv run python examples/simple_agent.py
cd packages/ts && NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password bun run examples/multi-turn-chat.ts

# Linters
cd packages/python && uv run ruff check . --fix --unsafe-fixes && uv run ruff format .
cd packages/ts && bunx tsc --noEmit
```

### Current branch / repo expectations
- Feature branch: `fix/migration-idempotency-and-put-writes` (needs PR)
- TS `v0.0.0` published to npm as `@luke_skywalker88/langgraph-checkpoint-neo4j`
- Python `v0.0.0` published to PyPI as `langgraph-checkpoint-neo4j`
- CI runs both Bun smoke + Vitest validation for TS
- `npm` GitHub environment with `NPM_TOKEN` secret is configured
- `pypi` GitHub environment with OIDC publishing is configured
- Neo4j Docker image is `neo4j:2026-community` everywhere
- **Migration idempotency fix is done** — blocker removed for v0.0.1 release

### What the next session does NOT need to worry about
- npm/PyPI publishing infrastructure — already working
- CI/release workflow structure — already stable
- Test runner strategy — Bun + Vitest split is settled
- Package naming — `@luke_skywalker88/langgraph-checkpoint-neo4j` (TS), `langgraph-checkpoint-neo4j` (Python)
- Migration idempotency — fixed
- Python `get_tuple()` returning `None` — fixed
- Python `put_writes` UPSERT/INSERT logic — fixed
- Multi-turn examples — both languages have working examples