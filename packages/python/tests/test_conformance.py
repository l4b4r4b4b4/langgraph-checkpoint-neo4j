"""Conformance tests — validate Neo4j checkpointer against the LangGraph conformance suite.

Registers ``AsyncNeo4jSaver`` with the ``@checkpointer_test`` decorator from
``langgraph-checkpoint-conformance`` and runs ``validate()`` to exercise all
base capabilities (put, put_writes, get_tuple, list, delete_thread).

Requires a running Neo4j instance (``bun run neo4j:up``).
"""

from __future__ import annotations

import contextlib
import os

import pytest
from neo4j import AsyncGraphDatabase

from langgraph.checkpoint.conformance import checkpointer_test, validate
from langgraph.checkpoint.conformance.report import ProgressCallbacks
from langgraph.checkpoint.neo4j.aio import AsyncNeo4jSaver

# ---------------------------------------------------------------------------
# Connection defaults — match docker-compose.yml / conftest.py
# ---------------------------------------------------------------------------

DEFAULT_NEO4J_URI = "bolt://localhost:7387"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = "password"
DEFAULT_NEO4J_DATABASE = "neo4j"


def _get_neo4j_uri() -> str:
    return os.environ.get("NEO4J_URI", DEFAULT_NEO4J_URI)


def _get_neo4j_auth() -> tuple[str, str]:
    return (
        os.environ.get("NEO4J_USER", DEFAULT_NEO4J_USER),
        os.environ.get("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
    )


def _get_neo4j_database() -> str:
    return os.environ.get("NEO4J_DATABASE", DEFAULT_NEO4J_DATABASE)


# ---------------------------------------------------------------------------
# Checkpoint node labels — used for per-test cleanup
# ---------------------------------------------------------------------------

CHECKPOINT_NODE_LABELS = (
    "Checkpoint",
    "CheckpointBlob",
    "CheckpointWrite",
    "CheckpointMigration",
)


# ---------------------------------------------------------------------------
# Lifespan — one-time setup/teardown for the entire validation run
# ---------------------------------------------------------------------------


async def neo4j_lifespan():
    """Verify Neo4j connectivity once before the full conformance suite runs."""
    driver = AsyncGraphDatabase.driver(_get_neo4j_uri(), auth=_get_neo4j_auth())
    try:
        await driver.verify_connectivity()
        yield
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# Checkpointer registration — factory called once per capability suite
# ---------------------------------------------------------------------------


@checkpointer_test(name="AsyncNeo4jSaver", lifespan=neo4j_lifespan)
async def neo4j_checkpointer():
    """Create a fresh AsyncNeo4jSaver for each capability test suite.

    Cleans up all checkpoint-related nodes before yielding so each
    capability suite starts with a clean database.
    """
    driver = AsyncGraphDatabase.driver(_get_neo4j_uri(), auth=_get_neo4j_auth())
    database = _get_neo4j_database()

    # Clean up any leftover data from previous test suites.
    async with driver.session(database=database) as session:
        for label in CHECKPOINT_NODE_LABELS:
            await session.run(f"MATCH (n:{label}) DETACH DELETE n")

    saver = AsyncNeo4jSaver(driver)

    # Once setup() is implemented (Task 02), this will create indexes/constraints.
    # For now, we catch the NotImplementedError so the factory doesn't blow up
    # before the conformance runner even gets to test individual capabilities.
    with contextlib.suppress(NotImplementedError):
        await saver.setup()

    try:
        yield saver
    finally:
        # Clean up after the suite.
        async with driver.session(database=database) as session:
            for label in CHECKPOINT_NODE_LABELS:
                await session.run(f"MATCH (n:{label}) DETACH DELETE n")
        await driver.close()


# ---------------------------------------------------------------------------
# Conformance test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conformance_base():
    """AsyncNeo4jSaver passes all base capability conformance tests.

    NOTE: This test is expected to FAIL until the checkpointer methods are
    implemented (Tasks 02-05).  The purpose at the skeleton stage (Task 01)
    is to verify that:
      1. ``uv run pytest`` collects and runs this test.
      2. The conformance framework can instantiate our checkpointer.
      3. Capability detection correctly identifies our overridden methods.
    """
    report = await validate(
        neo4j_checkpointer,
        progress=ProgressCallbacks.verbose(),
    )
    report.print_report()
    assert report.passed_all_base(), (
        f"Base conformance tests failed: {report.to_dict()}"
    )
