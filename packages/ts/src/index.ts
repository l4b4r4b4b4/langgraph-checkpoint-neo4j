/**
 * @luke_skywalker88/langgraph-checkpoint-neo4j
 *
 * Neo4j checkpointer for LangGraph — TypeScript implementation.
 * Drop-in replacement for the official Postgres checkpointer.
 *
 * @example
 * ```ts
 * import { Neo4jSaver } from "@luke_skywalker88/langgraph-checkpoint-neo4j";
 *
 * const checkpointer = Neo4jSaver.fromConnString(
 *   "bolt://localhost:7687",
 *   { username: "neo4j", password: "password" }
 * );
 * await checkpointer.setup();
 *
 * const graph = builder.compile({ checkpointer });
 * await graph.invoke(inputs, { configurable: { thread_id: "thread-1" } });
 *
 * await checkpointer.close();
 * ```
 *
 * @packageDocumentation
 */

import neo4j, {
  type Driver,
  type Session,
  type Record as Neo4jRecord,
  Integer,
} from "neo4j-driver";

import {
  BaseCheckpointSaver,
  type Checkpoint,
  type CheckpointListOptions,
  type CheckpointMetadata,
  type CheckpointTuple,
  type ChannelVersions,
  type PendingWrite,
  type CheckpointPendingWrite,
  WRITES_IDX_MAP,
  getCheckpointId,
  TASKS,
  maxChannelVersion,
} from "@langchain/langgraph-checkpoint";

import type { RunnableConfig } from "@langchain/core/runnables";
import type { SerializerProtocol } from "@langchain/langgraph-checkpoint";

import {
  MIGRATIONS,
  UPSERT_CHECKPOINT_BLOBS_CYPHER,
  UPSERT_CHECKPOINT_CYPHER,
  UPSERT_CHECKPOINT_WRITES_CYPHER,
  INSERT_CHECKPOINT_WRITES_CYPHER,
  GET_CHECKPOINT_BY_ID_CYPHER,
  GET_LATEST_CHECKPOINT_CYPHER,
  GET_CHANNEL_VALUES_CYPHER,
  GET_PENDING_WRITES_CYPHER,
  GET_PENDING_SENDS_CYPHER,
  LIST_CHECKPOINTS_BASE,
  DELETE_THREAD_CYPHER,
} from "./cypher.js";

// Re-export for consumers
export { Neo4jSaver };

// ---------------------------------------------------------------------------
// Helper: extract configurable fields safely
// ---------------------------------------------------------------------------

interface Configurable {
  thread_id: string;
  checkpoint_ns?: string;
  checkpoint_id?: string;
}

function getConfigurable(config: RunnableConfig): Configurable {
  const configurable = (config as Record<string, unknown>)
    .configurable as Configurable | undefined;
  if (!configurable) {
    throw new Error("Missing 'configurable' in config");
  }
  if (!configurable.thread_id) {
    throw new Error("Missing 'thread_id' in config.configurable");
  }
  return configurable;
}

// ---------------------------------------------------------------------------
// Helper: convert Neo4j Integer to JS number
// ---------------------------------------------------------------------------

function toNumber(value: unknown): number {
  if (neo4j.isInt(value)) {
    return (value as Integer).toNumber();
  }
  return value as number;
}

// ---------------------------------------------------------------------------
// Helper: convert Neo4j bytes to Uint8Array
// ---------------------------------------------------------------------------

function toUint8Array(blob: unknown): Uint8Array {
  if (blob instanceof Uint8Array) return blob;
  if (blob instanceof ArrayBuffer) return new Uint8Array(blob);
  if (Array.isArray(blob)) return new Uint8Array(blob);
  if (
    typeof blob === "object" &&
    blob !== null &&
    "buffer" in blob &&
    (blob as { buffer: unknown }).buffer instanceof ArrayBuffer
  ) {
    // Handle Node.js Buffer-like objects without importing Buffer
    const bufferLike = blob as { buffer: ArrayBuffer; byteOffset: number; byteLength: number };
    return new Uint8Array(bufferLike.buffer, bufferLike.byteOffset, bufferLike.byteLength);
  }
  return blob as Uint8Array;
}

// ---------------------------------------------------------------------------
// Neo4jSaver
// ---------------------------------------------------------------------------

/**
 * Checkpoint saver that stores LangGraph checkpoints in Neo4j.
 *
 * Implements the full `BaseCheckpointSaver` interface using Neo4j nodes
 * with indexed properties. The data model mirrors the three-table Postgres
 * layout: `Checkpoint`, `CheckpointBlob`, and `CheckpointWrite` nodes.
 *
 * Use {@link Neo4jSaver.fromConnString} for convenient construction,
 * or pass an existing `neo4j.Driver` to the constructor.
 */
class Neo4jSaver extends BaseCheckpointSaver<number> {
  /** The Neo4j driver (connection pool). */
  readonly driver: Driver;

  /** Whether setup() has been called. */
  private isSetup = false;

  /** Whether we created the driver (and should close it). */
  private ownsDriver: boolean;

  // ── Constructor ──────────────────────────────────────────────────────

  /**
   * Create a `Neo4jSaver` from an existing `neo4j.Driver`.
   *
   * @param driver - A Neo4j driver instance.
   * @param serde - Optional custom serializer.
   */
  constructor(driver: Driver, serde?: SerializerProtocol) {
    super(serde);
    this.driver = driver;
    this.ownsDriver = false;
  }

  // ── Factory ──────────────────────────────────────────────────────────

  /**
   * Create a `Neo4jSaver` from a Neo4j bolt connection URI.
   *
   * The driver is created internally. Call {@link close} when done.
   *
   * @param uri - Bolt URI, e.g. `"bolt://localhost:7687"`.
   * @param auth - Credentials, e.g. `{ username: "neo4j", password: "pass" }`.
   * @param serde - Optional custom serializer.
   * @returns A configured `Neo4jSaver` instance.
   *
   * @example
   * ```ts
   * const saver = Neo4jSaver.fromConnString(
   *   "bolt://localhost:7687",
   *   { username: "neo4j", password: "password" },
   * );
   * await saver.setup();
   * // ... use with LangGraph ...
   * await saver.close();
   * ```
   */
  static fromConnString(
    uri: string,
    auth: { username: string; password: string },
    serde?: SerializerProtocol
  ): Neo4jSaver {
    const driver = neo4j.driver(
      uri,
      neo4j.auth.basic(auth.username, auth.password)
    );
    const saver = new Neo4jSaver(driver, serde);
    saver.ownsDriver = true;
    return saver;
  }

  // ── Lifecycle ────────────────────────────────────────────────────────

  /**
   * Close the underlying Neo4j driver.
   *
   * Only closes the driver if it was created by {@link fromConnString}.
   * If you passed your own driver to the constructor, you are responsible
   * for closing it.
   */
  async close(): Promise<void> {
    if (this.ownsDriver) {
      await this.driver.close();
    }
  }

  // ── Schema setup ─────────────────────────────────────────────────────

  /**
   * Create Neo4j indexes and constraints required by the checkpointer.
   *
   * This method is **idempotent** — safe to call multiple times.
   * Migrations are tracked via `CheckpointMigration` nodes.
   */
  async setup(): Promise<void> {
    if (this.isSetup) return;

    const session = this.driver.session();
    try {
      // Always run migration v0 (the migration-tracking constraint).
      for (const statement of MIGRATIONS[0]) {
        await session.run(statement);
      }

      // Determine which migrations have already been applied.
      const result = await session.run(
        "MATCH (m:CheckpointMigration) " +
          "RETURN m.v AS v ORDER BY m.v DESC LIMIT 1"
      );
      let currentVersion = -1;
      if (result.records.length > 0) {
        currentVersion = toNumber(result.records[0].get("v"));
      }

      // Apply outstanding migrations.
      for (
        let versionNumber = currentVersion + 1;
        versionNumber < MIGRATIONS.length;
        versionNumber++
      ) {
        for (const statement of MIGRATIONS[versionNumber]) {
          await session.run(statement);
        }
        await session.run(
          "CREATE (m:CheckpointMigration {v: $v})",
          { v: neo4j.int(versionNumber) }
        );
      }

      this.isSetup = true;
    } finally {
      await session.close();
    }
  }

  // ── BaseCheckpointSaver — getTuple ───────────────────────────────────

  /**
   * Retrieve a checkpoint by configuration.
   *
   * @param config - Must contain `configurable.thread_id`. Optionally
   *   `checkpoint_ns` and `checkpoint_id`.
   * @returns The matching `CheckpointTuple`, or `undefined` if not found.
   */
  async getTuple(
    config: RunnableConfig
  ): Promise<CheckpointTuple | undefined> {
    const configurable = (config as Record<string, unknown>)
      .configurable as Configurable | undefined;
    const threadId = configurable?.thread_id;
    if (!threadId) {
      return undefined;
    }
    const checkpointNs = configurable.checkpoint_ns ?? "";
    const checkpointId = getCheckpointId(config);

    const session = this.driver.session();
    try {
      let result;
      if (checkpointId) {
        result = await session.run(GET_CHECKPOINT_BY_ID_CYPHER, {
          thread_id: threadId,
          checkpoint_ns: checkpointNs,
          checkpoint_id: checkpointId,
        });
      } else {
        result = await session.run(GET_LATEST_CHECKPOINT_CYPHER, {
          thread_id: threadId,
          checkpoint_ns: checkpointNs,
        });
      }

      if (result.records.length === 0) {
        return undefined;
      }

      return await this._buildCheckpointTuple(session, result.records[0]);
    } finally {
      await session.close();
    }
  }

  // ── BaseCheckpointSaver — list ───────────────────────────────────────

  /**
   * List checkpoints matching the given criteria.
   *
   * Results are yielded newest-first (descending checkpoint_id).
   *
   * @param config - Base config for filtering.
   * @param options - Optional `limit`, `before`, and `filter` parameters.
   */
  async *list(
    config: RunnableConfig,
    options?: CheckpointListOptions
  ): AsyncGenerator<CheckpointTuple> {
    const { limit, before, filter } = options ?? {};

    const { cypher, params } = this._buildListQuery(config, filter, before);

    let finalCypher = cypher;
    if (limit !== undefined && limit !== null && !filter) {
      // Only apply LIMIT in Cypher when there's no metadata filter.
      // Metadata filtering is done in JS post-query.
      finalCypher += ` LIMIT ${limit}`;
    }

    const session = this.driver.session();
    let records: Neo4jRecord[];
    try {
      const result = await session.run(finalCypher, params);
      records = result.records;
    } finally {
      await session.close();
    }

    let count = 0;
    for (const record of records) {
      // Post-filter by metadata if a filter dict was provided.
      if (filter) {
        const metadata = JSON.parse(record.get("metadata") as string);
        const matches = Object.entries(filter).every(
          ([key, value]) => metadata[key] === value
        );
        if (!matches) continue;
      }

      const tupleSession = this.driver.session();
      try {
        const tuple = await this._buildCheckpointTuple(tupleSession, record);
        yield tuple;
      } finally {
        await tupleSession.close();
      }

      count++;
      if (limit !== undefined && limit !== null && count >= limit) {
        break;
      }
    }
  }

  // ── BaseCheckpointSaver — put ────────────────────────────────────────

  /**
   * Store a checkpoint with its metadata and channel value blobs.
   *
   * @param config - Configuration for the checkpoint.
   * @param checkpoint - The checkpoint to store.
   * @param metadata - Additional metadata.
   * @param newVersions - New channel versions as of this write.
   * @returns Updated `RunnableConfig` pointing to the stored checkpoint.
   */
  async put(
    config: RunnableConfig,
    checkpoint: Checkpoint,
    metadata: CheckpointMetadata,
    newVersions: ChannelVersions
  ): Promise<RunnableConfig> {
    const configurable = getConfigurable(config);
    const threadId = configurable.thread_id;
    const checkpointNs = configurable.checkpoint_ns ?? "";
    const checkpointId = checkpoint.id;
    const parentCheckpointId = configurable.checkpoint_id ?? null;

    // Build a copy of the checkpoint without channel_values for storage.
    // Channel values are stored separately as CheckpointBlob nodes.
    const checkpointCopy = { ...checkpoint };
    const channelValues = checkpointCopy.channel_values;
    delete (checkpointCopy as Record<string, unknown>).channel_values;

    const checkpointJson = JSON.stringify(checkpointCopy);
    const metadataJson = JSON.stringify(metadata);

    // Dump channel blobs.
    const blobParams = await this._dumpBlobs(
      threadId,
      checkpointNs,
      channelValues,
      newVersions
    );

    const session = this.driver.session();
    try {
      // Upsert checkpoint blobs.
      for (const blobParam of blobParams) {
        await session.run(UPSERT_CHECKPOINT_BLOBS_CYPHER, blobParam);
      }

      // Upsert the checkpoint node.
      await session.run(UPSERT_CHECKPOINT_CYPHER, {
        thread_id: threadId,
        checkpoint_ns: checkpointNs,
        checkpoint_id: checkpointId,
        parent_checkpoint_id: parentCheckpointId,
        checkpoint: checkpointJson,
        metadata: metadataJson,
      });
    } finally {
      await session.close();
    }

    return {
      configurable: {
        thread_id: threadId,
        checkpoint_ns: checkpointNs,
        checkpoint_id: checkpointId,
      },
    };
  }

  // ── BaseCheckpointSaver — putWrites ──────────────────────────────────

  /**
   * Store intermediate writes linked to a checkpoint.
   *
   * @param config - Configuration of the related checkpoint.
   * @param writes - Array of `[channel, value]` pairs.
   * @param taskId - Identifier for the task creating the writes.
   */
  async putWrites(
    config: RunnableConfig,
    writes: PendingWrite[],
    taskId: string
  ): Promise<void> {
    const configurable = getConfigurable(config);
    const threadId = configurable.thread_id;
    const checkpointNs = configurable.checkpoint_ns ?? "";
    const checkpointId = configurable.checkpoint_id;

    if (!checkpointId) {
      throw new Error("Missing 'checkpoint_id' in config.configurable");
    }

    const writeParams = await this._dumpWrites(
      threadId,
      checkpointNs,
      checkpointId,
      taskId,
      writes
    );

    // Determine query: if ALL writes are special channels (in WRITES_IDX_MAP),
    // use UPSERT. Otherwise, use INSERT (idempotent no-op on conflict).
    const allSpecial = writes.every((w) => w[0] in WRITES_IDX_MAP);
    const queryTemplate = allSpecial
      ? UPSERT_CHECKPOINT_WRITES_CYPHER
      : INSERT_CHECKPOINT_WRITES_CYPHER;

    const session = this.driver.session();
    try {
      for (const writeParam of writeParams) {
        await session.run(queryTemplate, writeParam);
      }
    } finally {
      await session.close();
    }
  }

  // ── BaseCheckpointSaver — deleteThread ───────────────────────────────

  /**
   * Delete all checkpoints, blobs, and writes for a thread.
   *
   * @param threadId - The thread ID whose data should be deleted.
   */
  async deleteThread(threadId: string): Promise<void> {
    const session = this.driver.session();
    try {
      await session.run(DELETE_THREAD_CYPHER, { thread_id: threadId });
    } finally {
      await session.close();
    }
  }

  // ── Version helper ───────────────────────────────────────────────────

  /**
   * Generate the next version ID for a channel.
   *
   * Uses simple incrementing integers, matching the default
   * `BaseCheckpointSaver` behavior and the TS Postgres checkpointer.
   *
   * @param current - Current version number, or `undefined` for initial.
   * @returns The next version number.
   */
  override getNextVersion(current: number | undefined): number {
    return (current ?? 0) + 1;
  }

  // ── Serialization helpers ────────────────────────────────────────────

  /**
   * Serialize channel values into parameter objects for Cypher MERGE.
   */
  private async _dumpBlobs(
    threadId: string,
    checkpointNs: string,
    values: Record<string, unknown>,
    versions: ChannelVersions
  ): Promise<Record<string, unknown>[]> {
    if (!versions || Object.keys(versions).length === 0) {
      return [];
    }

    const result: Record<string, unknown>[] = [];
    for (const [channel, version] of Object.entries(versions)) {
      let typeStr: string;
      let blobBytes: Uint8Array | null;

      if (channel in values) {
        [typeStr, blobBytes] = await this.serde.dumpsTyped(values[channel]);
      } else {
        typeStr = "empty";
        blobBytes = null;
      }

      result.push({
        thread_id: threadId,
        checkpoint_ns: checkpointNs,
        channel,
        version: String(version),
        type: typeStr,
        blob: blobBytes,
      });
    }
    return result;
  }

  /**
   * Deserialize channel values from Neo4j query results.
   */
  private async _loadBlobs(
    blobRecords: Record<string, unknown>[]
  ): Promise<Record<string, unknown>> {
    if (!blobRecords || blobRecords.length === 0) {
      return {};
    }

    const channelValues: Record<string, unknown> = {};
    for (const record of blobRecords) {
      const typeStr = record.type as string;
      if (typeStr === "empty") continue;

      let blobData = record.blob;
      if (blobData != null) {
        blobData = toUint8Array(blobData);
      }
      channelValues[record.channel as string] = await this.serde.loadsTyped(
        typeStr,
        blobData as Uint8Array
      );
    }
    return channelValues;
  }

  /**
   * Serialize writes into parameter objects for Cypher statements.
   */
  private async _dumpWrites(
    threadId: string,
    checkpointNs: string,
    checkpointId: string,
    taskId: string,
    writes: PendingWrite[]
  ): Promise<Record<string, unknown>[]> {
    const result: Record<string, unknown>[] = [];
    for (let idx = 0; idx < writes.length; idx++) {
      const [channel, value] = writes[idx];
      const [typeStr, blobBytes] = await this.serde.dumpsTyped(value);
      result.push({
        thread_id: threadId,
        checkpoint_ns: checkpointNs,
        checkpoint_id: checkpointId,
        task_id: taskId,
        task_path: "",
        idx: WRITES_IDX_MAP[channel] ?? idx,
        channel,
        type: typeStr,
        blob: blobBytes,
      });
    }
    return result;
  }

  /**
   * Deserialize pending writes from Neo4j query results.
   */
  private async _loadWrites(
    writeRecords: Record<string, unknown>[]
  ): Promise<CheckpointPendingWrite[]> {
    if (!writeRecords || writeRecords.length === 0) {
      return [];
    }

    const result: CheckpointPendingWrite[] = [];
    for (const record of writeRecords) {
      let blobData = record.blob;
      if (blobData != null) {
        blobData = toUint8Array(blobData);
      }
      const value = await this.serde.loadsTyped(
        record.type as string,
        blobData as Uint8Array
      );
      result.push([
        record.task_id as string,
        record.channel as string,
        value,
      ]);
    }
    return result;
  }

  // ── Internal: build a CheckpointTuple from a Neo4j record ───────────

  /**
   * Construct a `CheckpointTuple` from a raw Neo4j checkpoint record.
   *
   * This fetches associated channel blobs and pending writes, then
   * deserializes everything into the expected format.
   */
  private async _buildCheckpointTuple(
    session: Session,
    record: Neo4jRecord
  ): Promise<CheckpointTuple> {
    const threadId = record.get("thread_id") as string;
    const checkpointNs = record.get("checkpoint_ns") as string;
    const checkpointId = record.get("checkpoint_id") as string;
    const parentCheckpointId = record.get("parent_checkpoint_id") as
      | string
      | null;

    // Deserialize checkpoint and metadata from JSON strings.
    const checkpointDict = JSON.parse(
      record.get("checkpoint") as string
    ) as Checkpoint;
    const metadataDict = JSON.parse(
      record.get("metadata") as string
    ) as CheckpointMetadata;

    // Ensure channel_values key exists.
    if (!checkpointDict.channel_values) {
      checkpointDict.channel_values = {};
    }

    // Load channel values by looking up each channel/version pair.
    const channelVersions = checkpointDict.channel_versions ?? {};
    const blobRecords: Record<string, unknown>[] = [];

    for (const [channel, version] of Object.entries(channelVersions)) {
      if (channel === TASKS) {
        // TASKS channel is handled via pending sends migration.
        continue;
      }
      const blobResult = await session.run(GET_CHANNEL_VALUES_CYPHER, {
        thread_id: threadId,
        checkpoint_ns: checkpointNs,
        channel,
        version: String(version),
      });
      if (blobResult.records.length > 0) {
        const blobRecord = blobResult.records[0];
        blobRecords.push({
          channel: blobRecord.get("channel"),
          type: blobRecord.get("type"),
          blob: blobRecord.get("blob"),
        });
      }
    }

    checkpointDict.channel_values = await this._loadBlobs(blobRecords);

    // Load pending writes.
    const writesResult = await session.run(GET_PENDING_WRITES_CYPHER, {
      thread_id: threadId,
      checkpoint_ns: checkpointNs,
      checkpoint_id: checkpointId,
    });
    const writeRecords = writesResult.records.map((r) => ({
      task_id: r.get("task_id"),
      channel: r.get("channel"),
      type: r.get("type"),
      blob: r.get("blob"),
    }));
    const pendingWrites = await this._loadWrites(writeRecords);

    // Handle pending sends migration only for legacy checkpoints.
    // This mirrors upstream Postgres behavior and avoids mutating
    // modern checkpoints that should already be in post-migration shape.
    if (checkpointDict.v < 4 && parentCheckpointId) {
      const sendsResult = await session.run(GET_PENDING_SENDS_CYPHER, {
        thread_id: threadId,
        checkpoint_ids: [parentCheckpointId],
        tasks_channel: TASKS,
      });

      if (sendsResult.records.length > 0) {
        const pendingSends: Array<[string, Uint8Array]> = [];
        for (const sendRecord of sendsResult.records) {
          let blobData = sendRecord.get("blob");
          if (blobData != null) {
            blobData = toUint8Array(blobData);
          }
          pendingSends.push([
            sendRecord.get("type") as string,
            blobData as Uint8Array,
          ]);
        }

        if (pendingSends.length > 0) {
          await this._migratePendingSends(
            pendingSends,
            checkpointDict
          );
        }
      }
    }

    // Build config for this checkpoint.
    const checkpointConfig: RunnableConfig = {
      configurable: {
        thread_id: threadId,
        checkpoint_ns: checkpointNs,
        checkpoint_id: checkpointId,
      },
    };

    // Build parent config if applicable.
    let parentConfig: RunnableConfig | undefined;
    if (parentCheckpointId) {
      parentConfig = {
        configurable: {
          thread_id: threadId,
          checkpoint_ns: checkpointNs,
          checkpoint_id: parentCheckpointId,
        },
      };
    }

    return {
      config: checkpointConfig,
      checkpoint: checkpointDict,
      metadata: metadataDict,
      parentConfig,
      pendingWrites,
    };
  }

  // ── Internal: pending sends migration ────────────────────────────────

  /**
   * Attach pending sends to a checkpoint's channel_values.
   *
   * Mirrors the Python checkpointer's `_migrate_pending_sends`.
   */
  private async _migratePendingSends(
    pendingSends: Array<[string, Uint8Array]>,
    checkpoint: Checkpoint
  ): Promise<void> {
    if (pendingSends.length === 0) return;

    checkpoint.channel_values ??= {};
    checkpoint.channel_versions ??= {};

    // Deserialize sends and add them to channel_values.
    const deserialized: unknown[] = [];
    for (const [typeStr, blobData] of pendingSends) {
      deserialized.push(await this.serde.loadsTyped(typeStr, blobData));
    }

    checkpoint.channel_values[TASKS] = deserialized;

    // Add a version entry for the TASKS channel.
    const versionValues = Object.values(checkpoint.channel_versions) as number[];
    checkpoint.channel_versions[TASKS] =
      versionValues.length > 0
        ? maxChannelVersion(...versionValues)
        : this.getNextVersion(undefined);
  }

  // ── Internal: build list query ───────────────────────────────────────

  /**
   * Build a Cypher `MATCH … WHERE … RETURN` query for `list()`.
   */
  private _buildListQuery(
    config: RunnableConfig | undefined,
    filter: Record<string, unknown> | undefined,
    before: RunnableConfig | undefined
  ): { cypher: string; params: Record<string, unknown> } {
    const wheres: string[] = [];
    const params: Record<string, unknown> = {};

    if (config) {
      const configurable = (config as Record<string, unknown>)
        .configurable as Configurable | undefined;

      if (configurable) {
        if (configurable.thread_id) {
          wheres.push("c.thread_id = $filter_thread_id");
          params.filter_thread_id = configurable.thread_id;
        }

        if (configurable.checkpoint_ns !== undefined) {
          wheres.push("c.checkpoint_ns = $filter_checkpoint_ns");
          params.filter_checkpoint_ns = configurable.checkpoint_ns;
        }

        const checkpointId = getCheckpointId(config);
        if (checkpointId) {
          wheres.push("c.checkpoint_id = $filter_checkpoint_id");
          params.filter_checkpoint_id = checkpointId;
        }
      }
    }

    if (before) {
      const beforeId = getCheckpointId(before);
      if (beforeId) {
        wheres.push("c.checkpoint_id < $before_checkpoint_id");
        params.before_checkpoint_id = beforeId;
      }
    }

    let whereClause = "";
    if (wheres.length > 0) {
      whereClause = " WHERE " + wheres.join(" AND ");
    }

    const cypher =
      LIST_CHECKPOINTS_BASE +
      whereClause +
      " RETURN c.thread_id AS thread_id," +
      " c.checkpoint_ns AS checkpoint_ns," +
      " c.checkpoint_id AS checkpoint_id," +
      " c.parent_checkpoint_id AS parent_checkpoint_id," +
      " c.checkpoint AS checkpoint," +
      " c.metadata AS metadata" +
      " ORDER BY c.checkpoint_id DESC";

    return { cypher, params };
  }
}
