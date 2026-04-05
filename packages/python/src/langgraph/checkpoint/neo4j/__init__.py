"""Neo4j checkpointer for LangGraph — drop-in replacement for the Postgres checkpointer.

This module provides ``Neo4jSaver``, a synchronous checkpoint saver backed by
Neo4j.  For the async variant see :mod:`langgraph.checkpoint.neo4j.aio`.

Example::

    from neo4j import GraphDatabase
    from langgraph.checkpoint.neo4j import Neo4jSaver

    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
    with Neo4jSaver(driver) as saver:
        saver.setup()
        # ... use with LangGraph ...
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_serializable_checkpoint_metadata,
)
from langgraph.checkpoint.neo4j.base import (
    DELETE_THREAD_CYPHER,
    GET_CHANNEL_VALUES_CYPHER,
    GET_CHECKPOINT_BY_ID_CYPHER,
    GET_LATEST_CHECKPOINT_CYPHER,
    GET_PENDING_SENDS_CYPHER,
    GET_PENDING_WRITES_CYPHER,
    INSERT_CHECKPOINT_WRITES_CYPHER,
    UPSERT_CHECKPOINT_BLOBS_CYPHER,
    UPSERT_CHECKPOINT_CYPHER,
    UPSERT_CHECKPOINT_WRITES_CYPHER,
    BaseNeo4jSaver,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.checkpoint.serde.types import TASKS
from neo4j import Driver, GraphDatabase

__all__ = [
    "Neo4jSaver",
]


class Neo4jSaver(BaseNeo4jSaver):
    """Synchronous checkpoint saver that stores checkpoints in Neo4j.

    This class implements the full ``BaseCheckpointSaver`` interface using
    Neo4j as the storage backend.  It translates the three-table Postgres
    model (checkpoints, checkpoint_blobs, checkpoint_writes) into Neo4j
    nodes with indexed properties.

    Args:
        driver: A ``neo4j.Driver`` instance (connection pool).
        serde: Optional custom serializer.  Defaults to the LangGraph
            ``JsonPlusSerializer``.

    Example::

        from neo4j import GraphDatabase
        from langgraph.checkpoint.neo4j import Neo4jSaver

        driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "password"),
        )
        with Neo4jSaver(driver) as saver:
            saver.setup()
            config = {"configurable": {"thread_id": "my-thread"}}
            # pass *saver* as the checkpointer when building a LangGraph graph
    """

    driver: Driver
    lock: threading.Lock
    _owns_driver: bool

    def __init__(
        self,
        driver: Driver,
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self.driver = driver
        self.lock = threading.Lock()
        self._owns_driver = False

    # -- Factory ------------------------------------------------------------

    @classmethod
    @contextmanager
    def from_conn_string(
        cls,
        conn_string: str,
        *,
        auth: tuple[str, str] = ("neo4j", "neo4j"),
    ) -> Iterator[Neo4jSaver]:
        """Create a ``Neo4jSaver`` from a Neo4j connection URI.

        The driver is created internally and closed when the context
        manager exits.

        Args:
            conn_string: Neo4j bolt URI, e.g. ``"bolt://localhost:7687"``.
            auth: ``(username, password)`` tuple for authentication.

        Yields:
            A configured ``Neo4jSaver`` instance.

        Example::

            with Neo4jSaver.from_conn_string(
                "bolt://localhost:7687",
                auth=("neo4j", "password"),
            ) as saver:
                saver.setup()
        """
        driver = GraphDatabase.driver(conn_string, auth=auth)
        saver = cls(driver)
        saver._owns_driver = True
        try:
            yield saver
        finally:
            driver.close()

    # -- Context manager ----------------------------------------------------

    def __enter__(self) -> Neo4jSaver:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if self._owns_driver:
            self.driver.close()

    # -- Schema setup -------------------------------------------------------

    def setup(self) -> None:
        """Create Neo4j indexes and constraints required by the checkpointer.

        This method is **idempotent** -- it is safe to call multiple times.
        Migrations are tracked via ``CheckpointMigration`` nodes.  Only
        migrations whose version number is higher than the last recorded
        version are executed.
        """
        with self.driver.session() as session:
            # Always run migration 0 (the migration-tracking constraint).
            for statement in self.MIGRATIONS[0]:
                session.run(statement)

            # Determine which migrations have already been applied.
            result = session.run(
                "MATCH (m:CheckpointMigration) "
                "RETURN m.v AS v ORDER BY m.v DESC LIMIT 1"
            )
            record = result.single()
            current_version = record["v"] if record else -1

            # Apply outstanding migrations.
            for version_number in range(current_version + 1, len(self.MIGRATIONS)):
                for statement in self.MIGRATIONS[version_number]:
                    session.run(statement)
                session.run(
                    "MERGE (m:CheckpointMigration {v: $v})",
                    {"v": version_number},
                )

    # -- BaseCheckpointSaver interface (sync) --------------------------------

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Fetch a checkpoint tuple using the given configuration.

        Args:
            config: Configuration specifying which checkpoint to retrieve.
                Must contain ``configurable.thread_id``; optionally
                ``checkpoint_ns`` and ``checkpoint_id``.

        Returns:
            The matching ``CheckpointTuple``, or ``None`` if not found.
        """
        configurable = config["configurable"]
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)

        with self.driver.session() as session:
            # Fetch the checkpoint node.
            if checkpoint_id:
                result = session.run(
                    GET_CHECKPOINT_BY_ID_CYPHER,
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    },
                )
            else:
                result = session.run(
                    GET_LATEST_CHECKPOINT_CYPHER,
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                    },
                )

            record = result.single()
            if record is None:
                return None

            return self._build_checkpoint_tuple(session, dict(record))

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints that match the given criteria.

        Args:
            config: Base configuration for filtering checkpoints.
            filter: Additional metadata key/value filtering.
            before: List checkpoints created before this configuration.
            limit: Maximum number of checkpoints to return.

        Yields:
            Matching ``CheckpointTuple`` instances, most recent first.
        """
        cypher, params = self._build_list_query(config, filter, before)

        if limit is not None and not filter:
            # Only apply LIMIT in Cypher when there's no metadata filter
            # (metadata filtering is done in Python post-query).
            cypher += f" LIMIT {limit}"

        with self.driver.session() as session:
            result = session.run(cypher, params)
            records = [dict(r) for r in result]

        count = 0
        for record_data in records:
            # Post-filter by metadata if a filter dict was provided.
            if filter:
                metadata = json.loads(record_data["metadata"])
                if not all(metadata.get(key) == value for key, value in filter.items()):
                    continue

            with self.driver.session() as session:
                checkpoint_tuple = self._build_checkpoint_tuple(session, record_data)
            yield checkpoint_tuple

            count += 1
            if limit is not None and count >= limit:
                break

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Store a checkpoint with its configuration and metadata.

        Args:
            config: Configuration for the checkpoint.
            checkpoint: The checkpoint to store.
            metadata: Additional metadata for the checkpoint.
            new_versions: New channel versions as of this write.

        Returns:
            Updated ``RunnableConfig`` pointing to the stored checkpoint.
        """
        configurable = config["configurable"]
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = configurable.get("checkpoint_id")

        # Merge run-level metadata from the config.
        serializable_metadata = get_serializable_checkpoint_metadata(config, metadata)

        # Build a copy of the checkpoint without channel_values for storage.
        # Channel values are stored separately as CheckpointBlob nodes.
        checkpoint_copy = checkpoint.copy()
        channel_values = checkpoint_copy.pop("channel_values", {})
        checkpoint_json = json.dumps(checkpoint_copy)
        metadata_json = json.dumps(serializable_metadata)

        # Dump channel blobs (all values, not just non-primitives).
        blob_params = self._dump_blobs(
            thread_id,
            checkpoint_ns,
            channel_values,
            new_versions,
        )

        with self.driver.session() as session:
            # Upsert checkpoint blobs.
            for blob_param in blob_params:
                session.run(UPSERT_CHECKPOINT_BLOBS_CYPHER, blob_param)

            # Upsert the checkpoint node.
            session.run(
                UPSERT_CHECKPOINT_CYPHER,
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "parent_checkpoint_id": parent_checkpoint_id,
                    "checkpoint": checkpoint_json,
                    "metadata": metadata_json,
                },
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            },
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store intermediate writes linked to a checkpoint.

        Args:
            config: Configuration of the related checkpoint.
            writes: List of ``(channel, value)`` pairs to store.
            task_id: Identifier for the task creating the writes.
            task_path: Path of the task creating the writes.
        """
        configurable = config["configurable"]
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = configurable["checkpoint_id"]

        write_params = self._dump_writes(
            thread_id,
            checkpoint_ns,
            checkpoint_id,
            task_id,
            task_path,
            writes,
        )

        with self.driver.session() as session:
            for write_param in write_params:
                channel = write_param["channel"]
                # Use UPSERT for special channels (overwrites), INSERT
                # (idempotent no-op on conflict) for regular channels.
                # Matches upstream Postgres: WRITES_IDX_MAP channels
                # (ERROR, SCHEDULED, INTERRUPT, RESUME) get UPSERT.
                if channel in WRITES_IDX_MAP:
                    cypher = UPSERT_CHECKPOINT_WRITES_CYPHER
                else:
                    cypher = INSERT_CHECKPOINT_WRITES_CYPHER
                session.run(cypher, write_param)

    def delete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes for a thread.

        Args:
            thread_id: The thread ID whose data should be deleted.
        """
        with self.driver.session() as session:
            session.run(DELETE_THREAD_CYPHER, {"thread_id": thread_id})

    # -- Internal helpers ----------------------------------------------------

    def _build_checkpoint_tuple(
        self,
        session: Any,
        record: dict[str, Any],
    ) -> CheckpointTuple:
        """Construct a ``CheckpointTuple`` from a raw Neo4j checkpoint record.

        This fetches associated channel blobs and pending writes, then
        deserialises everything into the expected format.
        """
        thread_id = record["thread_id"]
        checkpoint_ns = record["checkpoint_ns"]
        checkpoint_id = record["checkpoint_id"]
        parent_checkpoint_id = record.get("parent_checkpoint_id")

        # Deserialise checkpoint and metadata from JSON strings.
        # These were stored via json.dumps(), not serde.dumps_typed().
        checkpoint_dict = json.loads(record["checkpoint"])
        metadata_dict = json.loads(record["metadata"])

        # Ensure channel_values key exists.
        if "channel_values" not in checkpoint_dict:
            checkpoint_dict["channel_values"] = {}

        # Load channel values by looking up each channel/version pair.
        channel_versions = checkpoint_dict.get("channel_versions", {})
        blob_records: list[dict[str, Any]] = []
        for channel, version in channel_versions.items():
            if channel == TASKS:
                # TASKS channel is handled via pending sends migration.
                continue
            result = session.run(
                GET_CHANNEL_VALUES_CYPHER,
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "channel": channel,
                    "version": str(version),
                },
            )
            blob_record = result.single()
            if blob_record is not None:
                blob_records.append(dict(blob_record))

        checkpoint_dict["channel_values"] = self._load_blobs(blob_records)

        # Load pending writes.
        result = session.run(
            GET_PENDING_WRITES_CYPHER,
            {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            },
        )
        write_records = [dict(r) for r in result]
        pending_writes = self._load_writes(write_records)

        # Handle pending sends migration: if there is a parent checkpoint,
        # look for TASKS writes on the parent and attach them as channel
        # values on this checkpoint.
        if parent_checkpoint_id:
            result = session.run(
                GET_PENDING_SENDS_CYPHER,
                {
                    "thread_id": thread_id,
                    "checkpoint_ids": [parent_checkpoint_id],
                    "tasks_channel": TASKS,
                },
            )
            sends_records = [dict(r) for r in result]
            if sends_records:
                pending_sends: list[tuple[str, bytes]] = []
                for send_record in sends_records:
                    blob_data = send_record["blob"]
                    if isinstance(blob_data, bytearray):
                        blob_data = bytes(blob_data)
                    pending_sends.append((send_record["type"], blob_data))
                self._migrate_pending_sends(
                    pending_sends,
                    checkpoint_dict,
                    checkpoint_dict["channel_values"],
                )

        # Build config for this checkpoint.
        checkpoint_config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            },
        }

        # Build parent config if applicable.
        parent_config: RunnableConfig | None = None
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                },
            }

        return CheckpointTuple(
            config=checkpoint_config,
            checkpoint=checkpoint_dict,
            metadata=metadata_dict,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )
