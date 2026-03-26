/**
 * Cypher queries and migrations for the Neo4j checkpointer.
 *
 * This module mirrors the role of the Python `base.py` — it provides
 * the Cypher statements, migration list, and query constants shared by
 * the sync and async Neo4j checkpointer implementations.
 *
 * @module
 */

// ---------------------------------------------------------------------------
// Neo4j Cypher Migrations
// ---------------------------------------------------------------------------
// Each entry is a list of Cypher statements that constitute one migration
// version.  `setup()` runs them in order, tracking completed versions
// via `CheckpointMigration` nodes.
//
// Neo4j Community Edition does not support composite-key uniqueness
// constraints across multiple properties.  We use *node-key constraints*
// (available since Neo4j 5.7 Community) which enforce existence + uniqueness
// on a combination of properties.
//
// Because Cypher DDL is auto-committed, each statement must be run in its
// own transaction (which `setup()` handles).
// ---------------------------------------------------------------------------

export const MIGRATIONS: string[][] = [
  // v0 — migration tracking node
  [
    "CREATE CONSTRAINT checkpoint_migration_v_unique " +
      "IF NOT EXISTS " +
      "FOR (m:CheckpointMigration) REQUIRE m.v IS UNIQUE",
  ],

  // v1 — Checkpoint node constraint + index
  [
    "CREATE CONSTRAINT checkpoint_pk " +
      "IF NOT EXISTS " +
      "FOR (c:Checkpoint) " +
      "REQUIRE (c.thread_id, c.checkpoint_ns, c.checkpoint_id) IS UNIQUE",
    "CREATE INDEX checkpoint_thread_id_idx " +
      "IF NOT EXISTS " +
      "FOR (c:Checkpoint) ON (c.thread_id)",
  ],

  // v2 — CheckpointBlob node constraint + index
  [
    "CREATE CONSTRAINT checkpoint_blob_pk " +
      "IF NOT EXISTS " +
      "FOR (b:CheckpointBlob) " +
      "REQUIRE (b.thread_id, b.checkpoint_ns, b.channel, b.version) IS UNIQUE",
    "CREATE INDEX checkpoint_blob_thread_id_idx " +
      "IF NOT EXISTS " +
      "FOR (b:CheckpointBlob) ON (b.thread_id)",
  ],

  // v3 — CheckpointWrite node constraint + index
  [
    "CREATE CONSTRAINT checkpoint_write_pk " +
      "IF NOT EXISTS " +
      "FOR (w:CheckpointWrite) " +
      "REQUIRE (w.thread_id, w.checkpoint_ns, w.checkpoint_id, w.task_id, w.idx) IS UNIQUE",
    "CREATE INDEX checkpoint_write_thread_id_idx " +
      "IF NOT EXISTS " +
      "FOR (w:CheckpointWrite) ON (w.thread_id)",
  ],

  // v4 — Eagerly register all property keys used in Cypher queries.
  //
  // The Neo4j query planner emits "property key does not exist" warnings
  // when a MATCH/RETURN references a property key that has never been set
  // on any node in the database.  This happens on cold starts — the very
  // first `getTuple()` call runs before any `put()` has created a
  // Checkpoint node.  Creating (then deleting) a temporary node with every
  // property key we use ensures the keys are registered in the schema
  // catalog, silencing the planner notifications.
  [
    "CREATE (dummy:_PropertyKeyInit {" +
      "  thread_id: '', checkpoint_ns: '', checkpoint_id: ''," +
      "  parent_checkpoint_id: '', checkpoint: '', metadata: ''," +
      "  channel: '', version: '', type: '', blob: ''," +
      "  task_id: '', task_path: '', idx: 0," +
      "  v: -1" +
      "}) RETURN dummy",
    "MATCH (dummy:_PropertyKeyInit) DELETE dummy",
  ],
];

// ---------------------------------------------------------------------------
// Cypher Queries — UPSERT operations
// ---------------------------------------------------------------------------

export const UPSERT_CHECKPOINT_BLOBS_CYPHER = `
MERGE (b:CheckpointBlob {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    channel: $channel,
    version: $version
})
ON CREATE SET b.type = $type, b.blob = $blob
`;

export const UPSERT_CHECKPOINT_CYPHER = `
MERGE (c:Checkpoint {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    checkpoint_id: $checkpoint_id
})
SET c.parent_checkpoint_id = $parent_checkpoint_id,
    c.checkpoint = $checkpoint,
    c.metadata = $metadata
`;

// UPSERT writes — the ON MATCH variant updates channel/type/blob so that
// re-putting the same (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
// refreshes the payload (matches Postgres ON CONFLICT DO UPDATE behaviour).
export const UPSERT_CHECKPOINT_WRITES_CYPHER = `
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
`;

// INSERT writes — idempotent (ON MATCH does nothing), used for channels
// where we should not overwrite an existing write.
export const INSERT_CHECKPOINT_WRITES_CYPHER = `
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
`;

// ---------------------------------------------------------------------------
// Cypher Queries — SELECT operations
// ---------------------------------------------------------------------------

// Retrieve a single checkpoint by its exact (thread_id, checkpoint_ns,
// checkpoint_id) composite key.
export const GET_CHECKPOINT_BY_ID_CYPHER = `
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
`;

// Retrieve the latest checkpoint for a given (thread_id, checkpoint_ns).
export const GET_LATEST_CHECKPOINT_CYPHER = `
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
`;

// Retrieve a single channel blob by its exact composite key.
export const GET_CHANNEL_VALUES_CYPHER = `
MATCH (b:CheckpointBlob {
    thread_id: $thread_id,
    checkpoint_ns: $checkpoint_ns,
    channel: $channel,
    version: $version
})
RETURN b.channel AS channel, b.type AS type, b.blob AS blob
`;

// Retrieve all pending writes for a specific checkpoint, ordered for
// deterministic replay.
export const GET_PENDING_WRITES_CYPHER = `
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
`;

// Pending sends — writes with channel == TASKS for specified checkpoint IDs
// (used for the pending_sends migration logic).
export const GET_PENDING_SENDS_CYPHER = `
MATCH (w:CheckpointWrite)
WHERE w.thread_id = $thread_id
  AND w.checkpoint_id IN $checkpoint_ids
  AND w.channel = $tasks_channel
RETURN w.checkpoint_id AS checkpoint_id,
       w.type AS type,
       w.blob AS blob
ORDER BY w.task_path, w.task_id, w.idx
`;

// ---------------------------------------------------------------------------
// Cypher Queries — LIST checkpoints
// ---------------------------------------------------------------------------
// The `list` method needs dynamic WHERE clauses.  We build the Cypher
// string at call time via `_buildListQuery()`, but always use parameters.

export const LIST_CHECKPOINTS_BASE = "MATCH (c:Checkpoint)";

// ---------------------------------------------------------------------------
// Cypher Queries — DELETE
// ---------------------------------------------------------------------------

export const DELETE_THREAD_CYPHER = `
MATCH (n)
WHERE (n:Checkpoint OR n:CheckpointBlob OR n:CheckpointWrite)
  AND n.thread_id = $thread_id
DETACH DELETE n
`;
