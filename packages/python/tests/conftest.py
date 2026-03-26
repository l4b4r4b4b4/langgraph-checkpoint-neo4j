"""Shared fixtures for Neo4j checkpointer tests.

Provides Neo4j driver fixtures and connection defaults used by both
the conformance tests and any Neo4j-specific integration tests.

The Neo4j instance is expected to be running locally via:
    bun run neo4j:up

Connection defaults can be overridden via environment variables:
    NEO4J_URI      — Bolt URI        (default: bolt://localhost:7387)
    NEO4J_USER     — Username        (default: neo4j)
    NEO4J_PASSWORD — Password        (default: password)
    NEO4J_DATABASE — Database name   (default: neo4j)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncGraphDatabase, Driver, GraphDatabase

# ---------------------------------------------------------------------------
# Connection defaults — match docker-compose.yml
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
# Sync driver fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def neo4j_driver() -> Iterator[Driver]:
    """Provide a sync Neo4j driver, closed after each test."""
    driver = GraphDatabase.driver(_get_neo4j_uri(), auth=_get_neo4j_auth())
    try:
        yield driver
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# Async driver fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def async_neo4j_driver() -> AsyncIterator[AsyncDriver]:
    """Provide an async Neo4j driver, closed after each test."""
    driver = AsyncGraphDatabase.driver(_get_neo4j_uri(), auth=_get_neo4j_auth())
    try:
        yield driver
    finally:
        await driver.close()


# ---------------------------------------------------------------------------
# Cleanup helper — wipe all checkpoint-related nodes between tests
# ---------------------------------------------------------------------------

CHECKPOINT_NODE_LABELS = (
    "Checkpoint",
    "CheckpointBlob",
    "CheckpointWrite",
    "CheckpointMigration",
)


@pytest.fixture(autouse=True)
def _clear_neo4j_data(neo4j_driver: Driver) -> Iterator[None]:
    """Delete all checkpoint nodes before each test for isolation.

    This runs automatically for every test.  It uses OPTIONAL MATCH so
    that it does not fail if the labels don't exist yet (e.g. before
    ``setup()`` has been called).
    """
    database = _get_neo4j_database()
    with neo4j_driver.session(database=database) as session:
        for label in CHECKPOINT_NODE_LABELS:
            session.run(f"MATCH (n:{label}) DETACH DELETE n")
    yield
