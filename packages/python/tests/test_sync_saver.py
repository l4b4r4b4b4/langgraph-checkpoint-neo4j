"""Sync Neo4jSaver integration smoke tests.

These tests exercise the synchronous ``Neo4jSaver`` implementation directly.
They complement the async conformance test suite by covering the sync code
paths used by local examples and by consumers who use the sync LangGraph API.
"""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy

import pytest
from neo4j import Driver

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.neo4j import Neo4jSaver


@pytest.fixture(scope="function")
def sync_saver(neo4j_driver: Driver) -> Iterator[Neo4jSaver]:
    """Provide a synchronous Neo4jSaver with schema initialized."""
    saver = Neo4jSaver(neo4j_driver)
    saver.setup()
    yield saver


def test_sync_put_get_list_and_delete_thread(sync_saver: Neo4jSaver) -> None:
    """Store, retrieve, list, and delete checkpoints with the sync saver.

    This is a smoke/integration test for the main synchronous code paths:
    ``setup()``, ``put()``, ``get_tuple()``, ``list()``, and
    ``delete_thread()``.
    """
    thread_id = "sync-smoke-thread"
    checkpoint_namespace = ""
    base_config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_namespace,
        }
    }

    initial_checkpoint = empty_checkpoint()
    initial_checkpoint["channel_values"] = {
        "messages": ["hello"],
        "turn_count": 1,
    }
    initial_checkpoint["channel_versions"] = {
        "messages": sync_saver.get_next_version(None, None),
        "turn_count": sync_saver.get_next_version(None, None),
    }

    stored_initial_config = sync_saver.put(
        base_config,
        initial_checkpoint,
        {"source": "input", "step": 0},
        initial_checkpoint["channel_versions"],
    )

    retrieved_initial_tuple = sync_saver.get_tuple(stored_initial_config)
    assert retrieved_initial_tuple is not None
    assert retrieved_initial_tuple.config["configurable"]["thread_id"] == thread_id
    assert retrieved_initial_tuple.checkpoint["channel_values"]["messages"] == ["hello"]
    assert retrieved_initial_tuple.checkpoint["channel_values"]["turn_count"] == 1
    assert retrieved_initial_tuple.metadata["source"] == "input"
    assert retrieved_initial_tuple.metadata["step"] == 0
    assert retrieved_initial_tuple.parent_config is None

    next_checkpoint = deepcopy(retrieved_initial_tuple.checkpoint)
    next_checkpoint["id"] = empty_checkpoint()["id"]
    next_checkpoint["channel_values"] = {
        "messages": ["hello", "world"],
        "turn_count": 2,
    }
    next_checkpoint["channel_versions"] = {
        "messages": sync_saver.get_next_version(
            retrieved_initial_tuple.checkpoint["channel_versions"]["messages"],
            None,
        ),
        "turn_count": sync_saver.get_next_version(
            retrieved_initial_tuple.checkpoint["channel_versions"]["turn_count"],
            None,
        ),
    }

    stored_next_config = sync_saver.put(
        stored_initial_config,
        next_checkpoint,
        {"source": "loop", "step": 1},
        next_checkpoint["channel_versions"],
    )

    sync_saver.put_writes(
        stored_next_config,
        [("messages", ["pending-write"]), ("custom_channel", {"ok": True})],
        task_id="task-1",
        task_path="root/task-1",
    )

    retrieved_next_tuple = sync_saver.get_tuple(stored_next_config)
    assert retrieved_next_tuple is not None
    assert retrieved_next_tuple.metadata["source"] == "loop"
    assert retrieved_next_tuple.metadata["step"] == 1
    assert retrieved_next_tuple.parent_config is not None
    assert (
        retrieved_next_tuple.parent_config["configurable"]["checkpoint_id"]
        == stored_initial_config["configurable"]["checkpoint_id"]
    )
    assert retrieved_next_tuple.checkpoint["channel_values"]["messages"] == [
        "hello",
        "world",
    ]
    assert retrieved_next_tuple.checkpoint["channel_values"]["turn_count"] == 2
    assert len(retrieved_next_tuple.pending_writes) == 2
    assert (
        "task-1",
        "messages",
        ["pending-write"],
    ) in retrieved_next_tuple.pending_writes
    assert (
        "task-1",
        "custom_channel",
        {"ok": True},
    ) in retrieved_next_tuple.pending_writes

    latest_tuple = sync_saver.get_tuple(
        {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_namespace,
            }
        }
    )
    assert latest_tuple is not None
    assert (
        latest_tuple.config["configurable"]["checkpoint_id"]
        == stored_next_config["configurable"]["checkpoint_id"]
    )

    listed_tuples = list(
        sync_saver.list(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_namespace,
                }
            }
        )
    )
    assert len(listed_tuples) == 2
    assert (
        listed_tuples[0].config["configurable"]["checkpoint_id"]
        == stored_next_config["configurable"]["checkpoint_id"]
    )
    assert (
        listed_tuples[1].config["configurable"]["checkpoint_id"]
        == stored_initial_config["configurable"]["checkpoint_id"]
    )

    filtered_tuples = list(
        sync_saver.list(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_namespace,
                }
            },
            filter={"source": "loop"},
        )
    )
    assert len(filtered_tuples) == 1
    assert filtered_tuples[0].metadata["source"] == "loop"

    before_tuples = list(
        sync_saver.list(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_namespace,
                }
            },
            before=stored_next_config,
        )
    )
    assert len(before_tuples) == 1
    assert (
        before_tuples[0].config["configurable"]["checkpoint_id"]
        == stored_initial_config["configurable"]["checkpoint_id"]
    )

    limited_tuples = list(
        sync_saver.list(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_namespace,
                }
            },
            limit=1,
        )
    )
    assert len(limited_tuples) == 1
    assert (
        limited_tuples[0].config["configurable"]["checkpoint_id"]
        == stored_next_config["configurable"]["checkpoint_id"]
    )

    sync_saver.delete_thread(thread_id)

    assert sync_saver.get_tuple(stored_initial_config) is None
    assert sync_saver.get_tuple(stored_next_config) is None
    assert (
        list(
            sync_saver.list(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_namespace,
                    }
                }
            )
        )
        == []
    )


def test_sync_get_tuple_returns_none_for_missing_thread(sync_saver: Neo4jSaver) -> None:
    """Return ``None`` when no checkpoint exists for the requested thread."""
    result = sync_saver.get_tuple(
        {
            "configurable": {
                "thread_id": "does-not-exist",
                "checkpoint_ns": "",
            }
        }
    )
    assert result is None


def test_sync_setup_is_idempotent(sync_saver: Neo4jSaver) -> None:
    """Allow ``setup()`` to be called repeatedly without raising errors."""
    sync_saver.setup()
    sync_saver.setup()
