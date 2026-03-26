# langgraph-checkpoint-neo4j

Neo4j checkpointer for [LangGraph](https://github.com/langchain-ai/langgraph) — Python and TypeScript.

Drop-in replacement for the official Postgres checkpointer, backed by Neo4j's graph database.

[![CI](https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j/actions/workflows/ci.yml/badge.svg)](https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/v/langgraph-checkpoint-neo4j?label=pypi)](https://pypi.org/project/langgraph-checkpoint-neo4j/)
[![npm](https://img.shields.io/npm/v/@luke_skywalker88/langgraph-checkpoint-neo4j)](https://www.npmjs.com/package/@luke_skywalker88/langgraph-checkpoint-neo4j)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why Neo4j?

LangGraph ships with checkpointers for Postgres, SQLite, MongoDB, and Redis — but none for Neo4j. If your agent stack already uses Neo4j (e.g. for knowledge graphs via `langchain-neo4j`), running a separate Postgres instance just for checkpointing adds unnecessary infrastructure. This package lets you consolidate on Neo4j for both your knowledge graph **and** your agent state persistence.

## Features

- **Full `BaseCheckpointSaver` implementation** — passes the official LangGraph conformance test suite
- **Sync and async** — both `Neo4jSaver` and `AsyncNeo4jSaver` (Python), `Neo4jSaver` (TypeScript)
- **Graph-native storage** — checkpoints, checkpoint writes, and metadata stored as Neo4j nodes and relationships
- **Dual-language monorepo** — Python (`langgraph-checkpoint-neo4j`) and TypeScript (`@luke_skywalker88/langgraph-checkpoint-neo4j`) from one repo
- **Tested against upstream** — reference tests adapted from the official `checkpoint-postgres` packages

## Quick Start

### Python

```bash
pip install langgraph-checkpoint-neo4j
```

```python
from langgraph.checkpoint.neo4j import Neo4jSaver

# Using a connection URI
with Neo4jSaver.from_conn_string("bolt://localhost:7687", auth=("neo4j", "password")) as checkpointer:
    # Use with any LangGraph graph
    graph = builder.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "thread-1"}}
    graph.invoke(inputs, config)
```

#### Async

```python
from langgraph.checkpoint.neo4j.aio import AsyncNeo4jSaver

async with AsyncNeo4jSaver.from_conn_string("bolt://localhost:7687", auth=("neo4j", "password")) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
    await graph.ainvoke(inputs, config)
```

### TypeScript

```bash
npm install @luke_skywalker88/langgraph-checkpoint-neo4j
```

```typescript
import { Neo4jSaver } from "@luke_skywalker88/langgraph-checkpoint-neo4j";

const checkpointer = Neo4jSaver.fromConnString(
  "bolt://localhost:7687",
  { username: "neo4j", password: "password" }
);
await checkpointer.setup();

const graph = builder.compile({ checkpointer });
await graph.invoke(inputs, { configurable: { thread_id: "thread-1" } });

await checkpointer.close();
```

## Project Structure

```text
langgraph-checkpoint-neo4j/
├── packages/
│   ├── python/                         # Python package (langgraph-checkpoint-neo4j)
│   │   ├── src/langgraph/checkpoint/neo4j/
│   │   │   ├── __init__.py             #   Sync checkpointer (Neo4jSaver)
│   │   │   └── aio.py                  #   Async checkpointer (AsyncNeo4jSaver)
│   │   ├── tests/                      #   Pytest suite
│   │   └── pyproject.toml
│   └── ts/                             # TypeScript package (@luke_skywalker88/langgraph-checkpoint-neo4j)
│       ├── src/
│       │   ├── index.ts                #   Neo4jSaver implementation
│       │   ├── cypher.ts               #   Cypher queries + migrations
│       │   └── tests/
│       │       └── validate.test.ts    #   Bun smoke/regression tests
│       ├── tests/
│       │   └── validation.vitest.ts    #   Upstream validation suite (Vitest/Node)
│       ├── package.json
│       ├── tsconfig.json
│       └── vitest.config.ts
├── vendor/                             # Git submodules (reference implementations)
│   ├── langgraph-py/                   #   langchain-ai/langgraph (Python)
│   └── langgraph-js/                   #   langchain-ai/langgraphjs (TypeScript)
├── package.json                        # Bun workspace root
├── flake.nix                           # Nix dev environment
└── lefthook.yml                        # Git hooks
```

## Development

### Prerequisites

- **Nix** (recommended) or manually install: Python ≥ 3.11, [UV](https://docs.astral.sh/uv/), [Bun](https://bun.sh/) ≥ 1.1
- **Neo4j** — local instance or Docker (see below)

### Setup with Nix

```bash
git clone --recurse-submodules https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j.git
cd langgraph-checkpoint-neo4j
nix develop
```

### Setup without Nix

```bash
git clone --recurse-submodules https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j.git
cd langgraph-checkpoint-neo4j

# Root workspace
bun install

# Python package
cd packages/python
uv sync
```

### Start Neo4j (Docker)

```bash
docker compose up -d
```

This starts a Neo4j instance on `bolt://localhost:7687` with credentials `neo4j`/`password`.

### Run Tests

```bash
# All tests (Python + TS Bun smoke layer)
bun run test

# Python only
bun run test:python

# TypeScript Bun smoke/regression tests only
bun run test:ts

# TypeScript upstream official validation suite (Vitest/Node)
bun run test:ts:validation

# Both TypeScript layers (Bun smoke + upstream validation)
bun run test:ts:all
```

### Lint & Format

```bash
bun run lint
bun run format:python
```

## Vendor Submodules

The `vendor/` directory contains git submodules of the official LangGraph repos. These are used as reference implementations and to adapt the conformance/postgres test suites for Neo4j:

- `vendor/langgraph-py/libs/checkpoint-postgres/` — Python Postgres checkpointer + tests
- `vendor/langgraph-py/libs/checkpoint-conformance/` — Python conformance test suite
- `vendor/langgraph-js/libs/checkpoint-postgres/` — TypeScript Postgres checkpointer + tests
- `vendor/langgraph-js/libs/checkpoint-validation/` — TypeScript validation test suite

To update submodules to latest upstream:

```bash
git submodule update --remote
```

## Contributing

1. Fork the repo
2. Create a feature branch off `main`
3. Write tests first (adapt from the Postgres checkpointer tests)
4. Implement against the tests
5. Ensure `bun run test` passes
6. Open a PR

## TypeScript Release Quickstart (Guarded npm Publish)

Use this flow for releasing `@luke_skywalker88/langgraph-checkpoint-neo4j` safely:

1. **Prepare release PR**
   - Update `packages/ts/package.json` version to the target release version.
   - Set `"private": false` in `packages/ts/package.json` only when release is actually ready.
   - Keep `bun.lock` committed and up to date.

2. **Run required checks**
   - From repo root:
     - `bun run test:ts:all`
   - From `packages/ts`:
     - `bun run typecheck`
     - `bun run build`

3. **Tag release**
   - Create and push a tag in this format:
     - `ts-vX.Y.Z`

4. **Let release workflow publish**
   - The tag triggers `.github/workflows/release.yml` (`publish-ts` job).
   - Guard checks will fail publish if:
     - tag version != `packages/ts/package.json` version
     - package name is not `@luke_skywalker88/langgraph-checkpoint-neo4j`
     - `"private": true`
   - Workflow then runs:
     - Bun smoke tests
     - Upstream validation suite (Vitest/Node)
     - npm publish

5. **If release is delayed**
   - Revert `"private"` back to `true` on non-release branches to prevent accidental publish.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- [LangGraph](https://github.com/langchain-ai/langgraph) by LangChain for the checkpointer interface and reference implementations
- [Neo4j](https://neo4j.com/) for the graph database