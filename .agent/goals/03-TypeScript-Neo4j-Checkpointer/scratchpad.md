# Goal 03 — TypeScript Neo4j Checkpointer (v0.0.1)

**Status:** 🟡 In Progress
**Started:** 2026-03-26
**Completed:** —
**Priority:** P1 — Secondary to Python parity testing
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
- TypeScript / Bun users get `@langgraph/checkpoint-neo4j`

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
  - validation test wired to
    `@langchain/langgraph-checkpoint-validation`
- `packages/ts/package.json`
  - real package metadata and dependencies added
- `packages/ts/tsconfig.json`
  - updated for Bun runtime typing

### Validation status

The implementation was run against the upstream TS checkpoint validation suite.

**Result:** `699 / 714` tests passing (**97.9%**)

This is a strong first milestone: the implementation is no longer a placeholder
and already passes the overwhelming majority of the official validation suite.

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
- [ ] Published to npm as `@langgraph/checkpoint-neo4j`

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
- `private: true`
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

### Remaining failures
There are **15** known remaining failures.

#### Category 1: Bun / assertion-framework compatibility (`8` failures)
These failures come from validation tests written like:

- `expect(async () => ...).rejects.toThrow()`

In Bun's test runner this pattern is treated differently than in the framework
the validation suite appears to expect.

Observed symptom:
- tests fail with messages like "Expected promise, Received AsyncFunction"

Interpretation:
- our implementation likely throws correctly
- the test suite assertion style is not fully portable to Bun as-is

#### Category 2: Pending sends migration assertions (`4` failures)
Observed behavior:
- `__pregel_tasks` appears in `channel_values` and `channel_versions`
  after pending-send migration

Validation expectation:
- certain test cases expect the checkpoint object without those migrated fields

Interpretation:
- either:
  1. our pending sends migration in TS is slightly too eager, or
  2. the upstream TS Postgres implementation handles this subtly differently
     than our Python-based port

This needs code-level comparison against the upstream TS Postgres implementation.

#### Category 3: `thread_id` undefined edge cases (`2` failures)
Observed behavior:
- current guard logic throws when `thread_id` is missing / undefined

Validation expectation:
- some retrieval paths expect `undefined` result rather than a thrown error

Interpretation:
- input validation needs to be method-specific:
  - `put()` / `putWrites()` should likely throw on invalid config
  - `getTuple()` may need to return `undefined` for certain malformed cases
    instead of throwing

#### Category 4: `expect.soft()` not available in Bun (`1` failure)
Observed behavior:
- one validation test uses `expect.soft(...)`
- Bun's test runner does not expose that API

Interpretation:
- another test-framework compatibility issue, not a core saver logic issue

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

### Short-term next task for Goal 03
1. Re-run and categorize the 15 failures carefully
2. Fix method-specific malformed-config behavior:
   - probably `getTuple()` should not throw for some invalid cases
3. Compare pending sends migration logic against upstream TS Postgres
4. Decide how to handle validation-suite Bun incompatibilities:
   - patch test wrapper locally
   - or run validation under a different runner if needed

### Medium-term
5. Add a dedicated `packages/ts/tests/` structure
6. Clean up package exports and build boundaries
7. Decide when to flip `private: true` → publishable package
8. Add npm release workflow only when functionality is release-ready

### Priority guidance
Even with the strong TS progress, **Goal 02 remains the main next milestone**:
- Python parity testing drives the next release (`v0.0.1`)
- TS should continue in parallel only if it does not distract from Python parity

## Session Log

### 2026-03-26 — Initial TypeScript implementation session 🟢

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
- `packages/ts/src/tests/validate.test.ts` created
- TS package now has real dependencies and build metadata
- Validation result: **699 / 714 passing**

#### Important conclusions
- The TS implementation is no longer speculative — it is already mostly working
- Remaining failures are small and tractable
- Some failures are Bun test-runner compatibility issues, not necessarily saver bugs
- This work should be preserved and continued, but Python parity still comes first

---
## Handoff Notes

If continuing Goal 03 in a future session, start with:

1. Read this scratchpad fully
2. Re-run the TS validation suite against local Neo4j
3. Focus only on the remaining 15 failures
4. Do **not** re-implement the saver from scratch
5. Compare failing paths with upstream TS Postgres implementation before changing logic

### Useful commands

```text
# Start Neo4j locally
docker compose up -d neo4j

# Wait until browser endpoint responds
curl http://localhost:7373

# Typecheck
cd packages/ts && bunx tsc --noEmit

# Build
cd packages/ts && bunx tsc

# Run validation suite against local Neo4j docker-compose ports
cd packages/ts && NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password bun test
```

### Current branch / repo expectations
- TS implementation commit already exists on `main`
- do not assume all CI is ready for TS to be release-gating yet
- document any fix to the remaining 15 failures in this scratchpad