"""Shared Cypher queries, migrations, and serialization helpers for Neo4j checkpointers.

This module mirrors the role of ``langgraph.checkpoint.postgres.base`` — it
provides the SQL-equivalent Cypher statements, migration list, and the
``_dump_blobs`` / ``_load_blobs`` / ``_dump_writes`` / ``_load_writes`` helper
methods shared by both ``Neo4jSaver`` (sync) and ``AsyncNeo4jSaver`` (async).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    get_checkpoint_id,
)
from langgraph.checkpoint.serde.types import TASKS

# ---------------------------------------------------------------------------
# Neo4j Cypher Migrations
# ---------------------------------------------------------------------------
# Each entry is a list of Cypher statements that constitute one migration
# version.  ``setup()`` runs them in order, tracking completed versions
# via ``CheckpointMigration`` nodes.
#
# Neo4j Community Edition does not support composite-key uniqueness
# constraints across multiple properties.  We use *node-key constraints*
# (available since Neo4j 5.7 Community) which enforce existence + uniqueness
# on a combination of properties.  For older versions we fall back to
# range indexes that don't enforce uniqueness but still give us fast lookups.
#
# Because Cypher DDL is auto-committed, each statement must be run in its
# own transaction (which ``setup()`` handles).
# ---------------------------------------------------------------------------

MIGRATIONS: list[list[str]] = [
    # v0 — migration tracking node
    [
        (
            "CREATE CONSTRAINT checkpoint_migration_v_unique "
            "IF NOT EXISTS "
            "FOR (m:CheckpointMigration) REQUIRE m.v IS UNIQUE"
        ),
    ],
    # v1 — Checkpoint node constraint + index
    [
        (
            "CREATE CONSTRAINT checkpoint_pk "
            "IF NOT EXISTS "
            "FOR (c:Checkpoint) "
            "REQUIRE (c.thread_id, c.checkpoint_ns, c.checkpoint_id) IS UNIQUE"
        ),
        (
            "CREATE INDEX checkpoint_thread_id_idx "
            "IF NOT EXISTS "
            "FOR (c:Checkpoint) ON (c.thread_id)"
        ),
    ],
    # v2 — CheckpointBlob node constraint + index
    [
        (
            "CREATE CONSTRAINT checkpoint_blob_pk "
            "IF NOT EXISTS "
            "FOR (b:CheckpointBlob) "
            "REQUIRE (b.thread_id, b.checkpoint_ns, b.channel, b.version) IS UNIQUE"
        ),
        (
            "CREATE INDEX checkpoint_blob_thread_id_idx "
            "IF NOT EXISTS "
            "FOR (b:CheckpointBlob) ON (b.thread_id)"
        ),
    ],
    # v3 — CheckpointWrite node constraint + index
    [
        (
            "CREATE CONSTRAINT checkpoint_write_pk "
            "IF NOT EXISTS "
            "FOR (w:CheckpointWrite) "
            "REQUIRE (w.thread_id, w.checkpoint_ns, w.checkpoint_id, w.task_id, w.idx) IS UNIQUE"
        ),
        (
            "CREATE INDEX checkpoint_write_thread_id_idx "
            "IF NOT EXISTS "
            "FOR (w:CheckpointWrite) ON (w.thread_id)"
        ),
    ],
    # v4 — Eagerly register all property keys used in Cypher queries.
    #
    # The Neo4j query planner emits "property key does not exist" warnings
    # when a MATCH/RETURN references a property key that has never been set
    # on any node in the database.  This happens on cold starts — the very
    # first ``get_tuple()`` call runs before any ``put()`` has created a
    # Checkpoint node.  Creating (then deleting) a temporary node with every
    # property key we use ensures the keys are registered in the schema
    # catalog, silencing the planner notifications.
    [
        (
            "CREATE (dummy:_PropertyKeyInit {"
            "  thread_id: '', checkpoint_ns: '', checkpoint_id: '',"
            "  parent_checkpoint_id: '', checkpoint: '', metadata: '',"
            "  channel: '', version: '', type: '', blob: '',"
            "  task_id: '', task_path: '', idx: 0,"
            "  v: -1"
            "}) RETURN dummy"
        ),
        "MATCH (dummy:_PropertyKeyInit) DELETE dummy",
    ],
]

# ---------------------------------------------------------------------------
# Cypher Queries — UPSERT operations
# ---------------------------------------------------------------------------

UPSERT_CHECKPOINT_BLOBS_CYPHER = """
MERGE (b:CheckpointBlob {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    channel: $channel,
    version: $version
})
ON CREATE SET b.type = $type, b.blob = $blob
"""

UPSERT_CHECKPOINT_CYPHER = """
MERGE (c:Checkpoint {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    checkpoint_id: $checkpoint_id
})
SET c.parent_checkpoint_id = $parent_checkpoint_id,
    c.checkpoint = $checkpoint,
    c.metadata = $metadata
"""

# UPSERT writes — the ON MATCH variant updates channel/type/blob so that
# re-putting the same (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
# refreshes the payload (matches Postgres ON CONFLICT DO UPDATE behaviour).
UPSERT_CHECKPOINT_WRITES_CYPHER = """
MERGE (w:CheckpointWrite {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    checkpoint_id: $checkpoint_id,
    task_id: $task_id,
    idx: $idx
})
ON CREATE SET w.task_path = $task_path,
              w.channel = $channel,
              w.type = $type,
              w.blob = $blob
ON MATCH SET  w.channel = $channel,
              w.type = $type,
              w.blob = $blob
"""

# INSERT writes — idempotent (ON MATCH does nothing), used for channels
# where we should not overwrite an existing write.
INSERT_CHECKPOINT_WRITES_CYPHER = """
MERGE (w:CheckpointWrite {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    checkpoint_id: $checkpoint_id,
    task_id: $task_id,
    idx: $idx
})
ON CREATE SET w.task_path = $task_path,
              w.channel = $channel,
              w.type = $type,
              w.blob = $blob
"""

# ---------------------------------------------------------------------------
# Cypher Queries — SELECT operations
# ---------------------------------------------------------------------------

# Retrieve a single checkpoint with its channel blobs and pending writes.
#
# ``channel_versions_map`` is passed as a parameter — it is the JSON-decoded
# ``channel_versions`` dict from the checkpoint.  We unwind it to join with
# CheckpointBlob nodes at the matching version.
#
# The query returns one row per checkpoint.  ``channel_values`` and
# ``pending_writes`` are collected as lists.

GET_CHECKPOINT_BY_ID_CYPHER = """
MATCH (c:Checkpoint {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    checkpoint_id: $checkpoint_id
})
RETURN c.thread_id AS thread_id,
       c.checkpoint_ns AS checkpoint_ns,
       c.checkpoint_id AS checkpoint_id,
       c.parent_checkpoint_id AS parent_checkpoint_id,
       c.checkpoint AS checkpoint,
       c.metadata AS metadata
"""

GET_LATEST_CHECKPOINT_CYPHER = """
MATCH (c:Checkpoint {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns
})
RETURN c.thread_id AS thread_id,
       c.checkpoint_ns AS checkpoint_ns,
       c.checkpoint_id AS checkpoint_id,
       c.parent_checkpoint_id AS parent_checkpoint_id,
       c.checkpoint AS checkpoint,
       c.metadata AS metadata
ORDER BY c.checkpoint_id DESC
LIMIT 1
"""

GET_CHANNEL_VALUES_CYPHER = """
MATCH (b:CheckpointBlob {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    channel: $channel,
    version: $version
})
RETURN b.channel AS channel, b.type AS type, b.blob AS blob
"""

GET_PENDING_WRITES_CYPHER = """
MATCH (w:CheckpointWrite {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    checkpoint_id: $checkpoint_id
})
RETURN w.task_id AS task_id,
       w.channel AS channel,
       w.type AS type,
       w.blob AS blob
ORDER BY w.task_id, w.idx
"""

# Pending sends — writes with channel == TASKS for specified checkpoint IDs
# (used for the pending_sends migration logic).
GET_PENDING_SENDS_CYPHER = """
MATCH (w:CheckpointWrite)
WHERE w.thread_id = $thread_id
  AND w.checkpoint_id IN $checkpoint_ids
  AND w.channel = $tasks_channel
RETURN w.checkpoint_id AS checkpoint_id,
       w.type AS type,
       w.blob AS blob
ORDER BY w.task_path, w.task_id, w.idx
"""

# ---------------------------------------------------------------------------
# Cypher Queries — LIST checkpoints
# ---------------------------------------------------------------------------
# The ``list`` method needs dynamic WHERE clauses.  We build the Cypher
# string at call time via ``_build_list_query()``, but always use parameters.

LIST_CHECKPOINTS_BASE = "MATCH (c:Checkpoint)"

# ---------------------------------------------------------------------------
# Cypher Queries — DELETE
# ---------------------------------------------------------------------------

DELETE_THREAD_CYPHER = """
MATCH (n)
WHERE (n:Checkpoint OR n:CheckpointBlob OR n:CheckpointWrite)
  AND n.thread_id = $thread_id
DETACH DELETE n
"""

# ---------------------------------------------------------------------------
# Metadata input type
# ---------------------------------------------------------------------------

MetadataInput = dict[str, Any] | None


# ---------------------------------------------------------------------------
# BaseNeo4jSaver — shared logic for sync and async variants
# ---------------------------------------------------------------------------


class BaseNeo4jSaver(BaseCheckpointSaver[str]):
    """Shared logic for ``Neo4jSaver`` and ``AsyncNeo4jSaver``.

    This class holds Cypher constants, serialization helpers, and the
    ``get_next_version`` implementation.  It is **not** meant to be
    instantiated directly.
    """

    MIGRATIONS = MIGRATIONS

    # -- Serialisation helpers -----------------------------------------------

    def _dump_blobs(
        self,
        thread_id: str,
        checkpoint_ns: str,
        values: dict[str, Any],
        versions: ChannelVersions,
    ) -> list[dict[str, Any]]:
        """Serialise channel values into parameter dicts for ``MERGE`` statements.

        Each returned dict has keys matching the Cypher ``$param`` names in
        ``UPSERT_CHECKPOINT_BLOBS_CYPHER``.

        Returns an empty list when *versions* is empty (nothing to store).
        """
        if not versions:
            return []

        result: list[dict[str, Any]] = []
        for channel, version in versions.items():
            if channel in values:
                type_str, blob_bytes = self.serde.dumps_typed(values[channel])
            else:
                type_str = "empty"
                blob_bytes = None
            result.append(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "channel": channel,
                    "version": str(version),
                    "type": type_str,
                    "blob": blob_bytes,
                }
            )
        return result

    def _load_blobs(
        self,
        blob_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Deserialise channel values from Neo4j query results.

        *blob_records* is a list of dicts with keys ``channel``, ``type``,
        ``blob``.  Channels whose ``type`` is ``"empty"`` are skipped.
        """
        if not blob_records:
            return {}
        channel_values: dict[str, Any] = {}
        for record in blob_records:
            type_str = record["type"]
            if type_str == "empty":
                continue
            blob_data = record["blob"]
            # Neo4j may return bytearray; serde expects bytes.
            if isinstance(blob_data, bytearray):
                blob_data = bytes(blob_data)
            channel_values[record["channel"]] = self.serde.loads_typed(
                (type_str, blob_data)
            )
        return channel_values

    def _dump_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        task_id: str,
        task_path: str,
        writes: Sequence[tuple[str, Any]],
    ) -> list[dict[str, Any]]:
        """Serialise writes into parameter dicts for Cypher statements.

        Each dict has keys matching ``UPSERT_CHECKPOINT_WRITES_CYPHER``.
        """
        result: list[dict[str, Any]] = []
        for idx, (channel, value) in enumerate(writes):
            type_str, blob_bytes = self.serde.dumps_typed(value)
            result.append(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "task_path": task_path,
                    "idx": WRITES_IDX_MAP.get(channel, idx),
                    "channel": channel,
                    "type": type_str,
                    "blob": blob_bytes,
                }
            )
        return result

    def _load_writes(
        self,
        write_records: list[dict[str, Any]],
    ) -> list[tuple[str, str, Any]]:
        """Deserialise pending writes from Neo4j query results.

        Returns a list of ``(task_id, channel, value)`` triples.
        """
        if not write_records:
            return []
        result: list[tuple[str, str, Any]] = []
        for record in write_records:
            blob_data = record["blob"]
            if isinstance(blob_data, bytearray):
                blob_data = bytes(blob_data)
            result.append(
                (
                    record["task_id"],
                    record["channel"],
                    self.serde.loads_typed((record["type"], blob_data)),
                )
            )
        return result

    def _migrate_pending_sends(
        self,
        pending_sends: list[tuple[str, bytes]],
        checkpoint: dict[str, Any],
        channel_values: dict[str, Any],
    ) -> None:
        """Attach pending sends to a checkpoint's channel_values.

        *pending_sends* is a list of ``(type_str, blob_bytes)`` pairs from
        ``CheckpointWrite`` nodes with ``channel == TASKS``.

        This mirrors the Postgres checkpointer's ``_migrate_pending_sends``.
        """
        if not pending_sends:
            return
        # Deserialise and re-serialise as a single list blob.
        deserialized = [
            self.serde.loads_typed((type_str, blob_data))
            for type_str, blob_data in pending_sends
        ]
        channel_values[TASKS] = deserialized
        # Add a version entry for the TASKS channel.
        checkpoint["channel_versions"][TASKS] = (
            max(checkpoint["channel_versions"].values())
            if checkpoint["channel_versions"]
            else self.get_next_version(None, None)
        )

    # -- Version helper (same algorithm as Postgres checkpointer) -----------

    def get_next_version(self, current: str | None, channel: None) -> str:
        """Generate the next version ID for a channel.

        Uses the same integer-major + random-fractional scheme as the
        Postgres checkpointer for monotonically increasing, sortable
        version strings.

        Args:
            current: The current version string, or ``None`` for initial.
            channel: Unused (kept for interface compatibility).

        Returns:
            A version string of the form ``"<int>.<float>"``.
        """
        if current is None:
            current_version = 0
        elif isinstance(current, int):
            current_version = current
        else:
            current_version = int(current.split(".")[0])
        next_version = current_version + 1
        next_hash = random.random()
        return f"{next_version:032}.{next_hash:016}"

    # -- Query-building helpers ----------------------------------------------

    @staticmethod
    def _build_list_query(
        config: RunnableConfig | None,
        filter: MetadataInput,
        before: RunnableConfig | None,
    ) -> tuple[str, dict[str, Any]]:
        """Build a Cypher ``MATCH … WHERE … RETURN`` query for ``list()``.

        Returns ``(cypher_string, parameters_dict)``.
        """
        wheres: list[str] = []
        params: dict[str, Any] = {}

        if config:
            configurable = config["configurable"]
            wheres.append("c.thread_id = $filter_thread_id")
            params["filter_thread_id"] = configurable["thread_id"]

            checkpoint_ns = configurable.get("checkpoint_ns")
            if checkpoint_ns is not None:
                wheres.append("c.checkpoint_ns = $filter_checkpoint_ns")
                params["filter_checkpoint_ns"] = checkpoint_ns

            checkpoint_id = get_checkpoint_id(config)
            if checkpoint_id:
                wheres.append("c.checkpoint_id = $filter_checkpoint_id")
                params["filter_checkpoint_id"] = checkpoint_id

        if before is not None:
            before_id = get_checkpoint_id(before)
            if before_id:
                wheres.append("c.checkpoint_id < $before_checkpoint_id")
                params["before_checkpoint_id"] = before_id

        # Metadata filtering — we check individual keys because Neo4j
        # doesn't have a native JSON-contains operator.  The metadata is
        # stored as a JSON string, so we parse it and check properties.
        # For simplicity, we post-filter metadata in Python (see the
        # ``list`` / ``alist`` implementations).

        where_clause = ""
        if wheres:
            where_clause = " WHERE " + " AND ".join(wheres)

        cypher = (
            LIST_CHECKPOINTS_BASE
            + where_clause
            + " RETURN c.thread_id AS thread_id,"
            + " c.checkpoint_ns AS checkpoint_ns,"
            + " c.checkpoint_id AS checkpoint_id,"
            + " c.parent_checkpoint_id AS parent_checkpoint_id,"
            + " c.checkpoint AS checkpoint,"
            + " c.metadata AS metadata"
            + " ORDER BY c.checkpoint_id DESC"
        )

        return cypher, params
