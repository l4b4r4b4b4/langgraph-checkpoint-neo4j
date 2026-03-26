# `@luke_skywalker88/langgraph-checkpoint-neo4j` (TypeScript)

Neo4j checkpointer for LangGraph.js.

This package provides `Neo4jSaver`, a Neo4j-backed implementation of the LangGraph checkpoint saver interface, intended as a drop-in alternative to the Postgres checkpointer.

## Status

- ✅ Core saver implementation in `src/index.ts`
- ✅ Bun-native smoke/regression tests
- ✅ Full upstream checkpoint validation suite coverage (run with Vitest)
- 🚧 Publish-gated: package remains `private: true` until release checklist is completed

## Installation

Inside this monorepo, dependencies are managed with **Bun workspaces**.

From repo root:

```bash
bun install
```

## Usage

```ts
import { Neo4jSaver } from "@luke_skywalker88/langgraph-checkpoint-neo4j";

const saver = Neo4jSaver.fromConnString("bolt://localhost:7687", {
  username: "neo4j",
  password: "password",
});

await saver.setup();

// Use with a LangGraph graph
const graph = builder.compile({ checkpointer: saver });
await graph.invoke(inputs, { configurable: { thread_id: "thread-1" } });

await saver.close();
```

## Environment

Set these environment variables when running tests or local validation:

- `NEO4J_URI` (default: `bolt://localhost:7687`)
- `NEO4J_USER` (default: `neo4j`)
- `NEO4J_PASSWORD` (default: `password`)

For local development with repo `docker-compose.yml`, Neo4j Bolt is exposed at `bolt://localhost:7387`.

## Testing Strategy (Important)

This package intentionally uses **two test layers**:

1. **Bun smoke/regression tests** (fast, Bun-native)
2. **Upstream validation suite** under **Vitest/Node** (framework-compatible with upstream assertions)

This split exists because upstream validation assertions rely on Vitest semantics (`expect.soft`, async `.rejects` patterns) that are not fully compatible with Bun test behavior.

### Run tests from `packages/ts`

```bash
# Bun smoke/regression tests
bun run test:bun

# Upstream official validation suite (Vitest)
bun run test:validation

# Both
bun run test:all
```

### Run tests from repo root

```bash
# Bun smoke tests only (TS)
bun run test:ts

# Upstream TS validation only
bun run test:ts:validation

# Both TS layers
bun run test:ts:all
```

## CI Expectations

TypeScript CI is green only when all of the following pass:

1. Type check (`tsc --noEmit`)
2. Bun smoke tests (`bun run test:bun`)
3. Upstream validation suite (`bun x vitest run --config vitest.config.ts`)

In short: **both test layers are required**.

## Publish Checklist (npm)

Before changing `private` to `false` and publishing, verify all items:

- [ ] `packages/ts/package.json` version matches intended `ts-vX.Y.Z` release tag
- [ ] `packages/ts/package.json` has `private: false`
- [ ] `bun.lock` is committed and current
- [ ] `bun run typecheck` passes
- [ ] `bun run test:bun` passes
- [ ] `bun run test:validation` passes (`714/714` expected unless upstream suite changes)
- [ ] `bun run build` passes and `dist/` output is clean
- [ ] README usage examples are still accurate
- [ ] CI TypeScript job passes with `neo4j:2026-community`
- [ ] `NPM_TOKEN` secret is configured for release workflow

Recommended pre-release command sequence from repo root:

```bash
bun run test:ts:all
cd packages/ts && bun run typecheck && bun run build
```

Release gate policy:
- Keep `private: true` by default on development branches.
- Flip to `private: false` only in a release PR that also bumps version and is ready to tag/publish.
- If release is postponed, revert `private` back to `true`.

## Development Notes

- Language target: `ESNext`
- Module format: `ESNext`
- Strict mode: enabled
- Runtime driver: official `neo4j-driver`
- Validation test file: `tests/validation.vitest.ts`
- Bun smoke test file: `src/tests/validate.test.ts`

## Neo4j Requirements

- Tested with Neo4j Docker image tag: `neo4j:2026-community`
- `setup()` is idempotent and safe to call multiple times.
- Saver stores checkpoints, blobs, and writes in dedicated node labels with indexed lookup fields.

## License

MIT (repo-level license).