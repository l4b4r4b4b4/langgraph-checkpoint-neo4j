# langgraph-checkpoint-neo4j

[![PyPI](https://img.shields.io/pypi/v/langgraph-checkpoint-neo4j)](https://pypi.org/project/langgraph-checkpoint-neo4j/)
[![Python](https://img.shields.io/pypi/pyversions/langgraph-checkpoint-neo4j)](https://pypi.org/project/langgraph-checkpoint-neo4j/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j/blob/main/LICENSE)

Neo4j checkpointer for [LangGraph](https://github.com/langchain-ai/langgraph) — a drop-in replacement for the official Postgres checkpointer, backed by Neo4j.

Passes the full [LangGraph checkpoint conformance test suite](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-conformance) (59/59 tests).

## Installation

```bash
pip install langgraph-checkpoint-neo4j
```

Requires:
- Python ≥ 3.11
- Neo4j ≥ 5.7 (for composite uniqueness constraints)
- `langgraph-checkpoint` ≥ 2.0.0

## Quick Start

### Sync

```python
from langgraph.checkpoint.neo4j import Neo4jSaver

with Neo4jSaver.from_conn_string(
    "bolt://localhost:7687",
    auth=("neo4j", "password"),
) as checkpointer:
    checkpointer.setup()  # creates indexes/constraints (idempotent)

    # Use with any LangGraph graph
    graph = builder.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "my-thread"}}
    result = graph.invoke(inputs, config)
```

### Async

```python
from langgraph.checkpoint.neo4j.aio import AsyncNeo4jSaver

async with AsyncNeo4jSaver.from_conn_string(
    "bolt://localhost:7687",
    auth=("neo4j", "password"),
) as checkpointer:
    await checkpointer.setup()

    graph = builder.compile(checkpointer=checkpointer)
    result = await graph.ainvoke(inputs, config)
```

### Using an Existing Driver

If you already have a `neo4j.Driver` or `neo4j.AsyncDriver` (e.g. shared with a knowledge graph), pass it directly:

```python
from neo4j import GraphDatabase
from langgraph.checkpoint.neo4j import Neo4jSaver

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
saver = Neo4jSaver(driver)
saver.setup()

# ... use saver ...

driver.close()
```

## API Reference

### `Neo4jSaver` (sync)

```python
from langgraph.checkpoint.neo4j import Neo4jSaver
```

| Method | Description |
|--------|-------------|
| `Neo4jSaver(driver, *, serde=None)` | Constructor. Accepts a `neo4j.Driver`. |
| `Neo4jSaver.from_conn_string(uri, *, auth)` | Context manager factory from a bolt URI. |
| `setup()` | Create Neo4j indexes and constraints. Idempotent. |
| `get_tuple(config)` | Retrieve a checkpoint by config. |
| `list(config, *, filter, before, limit)` | List checkpoints matching criteria. |
| `put(config, checkpoint, metadata, new_versions)` | Store a checkpoint. |
| `put_writes(config, writes, task_id, task_path)` | Store intermediate writes. |
| `delete_thread(thread_id)` | Delete all data for a thread. |

### `AsyncNeo4jSaver` (async)

```python
from langgraph.checkpoint.neo4j.aio import AsyncNeo4jSaver
```

| Method | Description |
|--------|-------------|
| `AsyncNeo4jSaver(driver, *, serde=None)` | Constructor. Accepts a `neo4j.AsyncDriver`. |
| `AsyncNeo4jSaver.from_conn_string(uri, *, auth)` | Async context manager factory from a bolt URI. |
| `setup()` | Create Neo4j indexes and constraints. Idempotent. |
| `aget_tuple(config)` | Retrieve a checkpoint by config. |
| `alist(config, *, filter, before, limit)` | List checkpoints matching criteria. |
| `aput(config, checkpoint, metadata, new_versions)` | Store a checkpoint. |
| `aput_writes(config, writes, task_id, task_path)` | Store intermediate writes. |
| `adelete_thread(thread_id)` | Delete all data for a thread. |

## Neo4j Data Model

The checkpointer stores data as Neo4j nodes with indexed properties, translating the three-table Postgres model:

| Postgres Table | Neo4j Node Label | Key Properties |
|----------------|------------------|----------------|
| `checkpoints` | `Checkpoint` | `thread_id`, `checkpoint_ns`, `checkpoint_id`, `parent_checkpoint_id`, `checkpoint` (JSON), `metadata` (JSON) |
| `checkpoint_blobs` | `CheckpointBlob` | `thread_id`, `checkpoint_ns`, `channel`, `version`, `type`, `blob` (bytes) |
| `checkpoint_writes` | `CheckpointWrite` | `thread_id`, `checkpoint_ns`, `checkpoint_id`, `task_id`, `task_path`, `idx`, `channel`, `type`, `blob` (bytes) |
| `checkpoint_migrations` | `CheckpointMigration` | `v` (integer) |

### Constraints & Indexes

The `setup()` method creates the following (all idempotent):

- **Uniqueness constraints** on composite keys for `Checkpoint`, `CheckpointBlob`, and `CheckpointWrite` nodes
- **Range indexes** on `thread_id` for all three node types (fast thread-scoped lookups)

### Why Nodes Instead of Relationships?

The Postgres model uses three independent tables joined by compound keys. In Neo4j, using nodes with indexed properties gives us the same query patterns without adding relationship overhead. This keeps the implementation simple and the conformance tests passing. Relationships could be added later for graph-traversal use cases without breaking the core API.

## Configuration

### Environment Variables

The test fixtures support environment variable overrides for connecting to Neo4j:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_USER` | `neo4j` | Username |
| `NEO4J_PASSWORD` | `password` | Password |
| `NEO4J_DATABASE` | `neo4j` | Database name |

### Docker (for local development)

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5-community
```

Or use the project's docker-compose:

```bash
# from the repo root
docker compose up -d neo4j
```

## Conformance

This package passes the full LangGraph checkpoint conformance suite:

```
====================================================
  Checkpointer Validation: AsyncNeo4jSaver
====================================================
  BASE CAPABILITIES
    ✅ delete_thread
    ✅ get_tuple
    ✅ list
    ✅ put
    ✅ put_writes

  EXTENDED CAPABILITIES
    ⊘  copy_thread          (not implemented)
    ⊘  delete_for_runs      (not implemented)
    ⊘  prune                (not implemented)

  Result: FULL (5/5)
====================================================
```

Extended capabilities (`copy_thread`, `delete_for_runs`, `prune`) are not yet implemented. They are optional in the LangGraph spec and will be added in future releases.

## Development

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j.git
cd langgraph-checkpoint-neo4j/packages/python

# Install dependencies
uv sync

# Start Neo4j
docker compose -f ../../docker-compose.yml up -d neo4j

# Run tests
uv run pytest

# Lint & format
uv run ruff check . --fix --unsafe-fixes && uv run ruff format .

# Build
uv build
```

## License

MIT — see [LICENSE](https://github.com/l4b4r4b4b4/langgraph-checkpoint-neo4j/blob/main/LICENSE).