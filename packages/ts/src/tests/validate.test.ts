/// <reference types="bun-types" />

/**
 * Bun-native smoke and regression tests for Neo4jSaver.
 *
 * This file intentionally does NOT use the upstream validation package.
 * It focuses on fast local confidence checks for core behavior under Bun.
 */

import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import type { RunnableConfig } from "@langchain/core/runnables";
import {
  TASKS,
  type Checkpoint,
  type CheckpointTuple,
  uuid6,
} from "@langchain/langgraph-checkpoint";
import { Neo4jSaver } from "../index.js";

const neo4jUri = process.env.NEO4J_URI ?? "bolt://localhost:7687";
const neo4jUser = process.env.NEO4J_USER ?? "neo4j";
const neo4jPassword = process.env.NEO4J_PASSWORD ?? "password";

function createCheckpoint(checkpointId: string, channelValues: Record<string, unknown>): Checkpoint {
  return {
    v: 4,
    id: checkpointId,
    ts: new Date().toISOString(),
    channel_values: channelValues,
    channel_versions: Object.fromEntries(
      Object.keys(channelValues).map((channelName) => [channelName, 1])
    ),
    versions_seen: {},
  };
}

async function createSaver(): Promise<Neo4jSaver> {
  const saver = Neo4jSaver.fromConnString(neo4jUri, {
    username: neo4jUser,
    password: neo4jPassword,
  });
  await saver.setup();
  return saver;
}

async function clearCheckpointData(saver: Neo4jSaver): Promise<void> {
  const cleanupSession = saver.driver.session();
  try {
    await cleanupSession.run(
      "MATCH (node) WHERE node:Checkpoint OR node:CheckpointBlob OR node:CheckpointWrite DETACH DELETE node"
    );
  } finally {
    await cleanupSession.close();
  }
}

describe("Neo4jSaver Bun smoke tests", () => {
  let saver: Neo4jSaver;

  beforeEach(async () => {
    saver = await createSaver();
    await clearCheckpointData(saver);
  });

  afterEach(async () => {
    await clearCheckpointData(saver);
    await saver.close();
  });

  it("setup is idempotent", async () => {
    await saver.setup();
    await saver.setup();
  });

  it("put + getTuple round-trips checkpoint and metadata", async () => {
    const threadIdentifier = `thread-${uuid6(-3)}`;
    const checkpointIdentifier = uuid6(-3);

    const inputCheckpoint = createCheckpoint(checkpointIdentifier, {
      animals: ["dog"],
    });

    const storedConfig = await saver.put(
      {
        configurable: {
          thread_id: threadIdentifier,
          checkpoint_ns: "",
        },
      },
      inputCheckpoint,
      { source: "loop", step: 1, parents: {} },
      { animals: 1 }
    );

    const retrievedTuple = await saver.getTuple(storedConfig);

    expect(retrievedTuple).toBeDefined();
    expect(retrievedTuple?.checkpoint).toEqual(inputCheckpoint);
    expect(retrievedTuple?.metadata).toEqual({
      source: "loop",
      step: 1,
      parents: {},
    });
    expect(retrievedTuple?.config).toEqual({
      configurable: {
        thread_id: threadIdentifier,
        checkpoint_ns: "",
        checkpoint_id: checkpointIdentifier,
      },
    });
  });

  it("putWrites stores writes that are retrievable from getTuple", async () => {
    const threadIdentifier = `thread-${uuid6(-3)}`;
    const checkpointIdentifier = uuid6(-3);

    const inputCheckpoint = createCheckpoint(checkpointIdentifier, {
      animals: ["dog"],
    });

    const storedConfig = await saver.put(
      {
        configurable: {
          thread_id: threadIdentifier,
          checkpoint_ns: "",
        },
      },
      inputCheckpoint,
      { source: "loop", step: 1, parents: {} },
      { animals: 1 }
    );

    await saver.putWrites(
      storedConfig,
      [["animals", ["dog", "cat"]]],
      "animal-task"
    );

    const retrievedTuple = await saver.getTuple(storedConfig);

    expect(retrievedTuple).toBeDefined();
    expect(retrievedTuple?.pendingWrites).toEqual([
      ["animal-task", "animals", ["dog", "cat"]],
    ]);
  });

  it("getTuple returns undefined when thread_id is missing", async () => {
    const missingThreadIdConfig: RunnableConfig = {
      configurable: {
        checkpoint_ns: "",
      },
    };

    const tupleWithoutThread = await saver.getTuple(missingThreadIdConfig);
    expect(tupleWithoutThread).toBeUndefined();
  });

  it("list returns newest first and supports metadata filter", async () => {
    const threadIdentifier = `thread-${uuid6(-3)}`;

    const firstCheckpointIdentifier = uuid6(-3);
    const secondCheckpointIdentifier = uuid6(-2);

    const firstCheckpoint = createCheckpoint(firstCheckpointIdentifier, {
      state: "first",
    });
    const secondCheckpoint = createCheckpoint(secondCheckpointIdentifier, {
      state: "second",
    });

    let currentConfig = await saver.put(
      {
        configurable: {
          thread_id: threadIdentifier,
          checkpoint_ns: "",
        },
      },
      firstCheckpoint,
      { source: "input", step: 1, parents: {} },
      { state: 1 }
    );

    currentConfig = await saver.put(
      currentConfig,
      secondCheckpoint,
      { source: "loop", step: 2, parents: {} },
      { state: 2 }
    );

    const unfilteredTuples: CheckpointTuple[] = [];
    for await (const listedTuple of saver.list({
      configurable: { thread_id: threadIdentifier, checkpoint_ns: "" },
    })) {
      unfilteredTuples.push(listedTuple);
    }

    expect(unfilteredTuples.length).toBe(2);
    expect(unfilteredTuples[0].checkpoint.id).toBe(secondCheckpointIdentifier);
    expect(unfilteredTuples[1].checkpoint.id).toBe(firstCheckpointIdentifier);

    const filteredTuples: CheckpointTuple[] = [];
    for await (const listedTuple of saver.list(
      { configurable: { thread_id: threadIdentifier, checkpoint_ns: "" } },
      { filter: { source: "input" } }
    )) {
      filteredTuples.push(listedTuple);
    }

    expect(filteredTuples.length).toBe(1);
    expect(filteredTuples[0].checkpoint.id).toBe(firstCheckpointIdentifier);
  });

  it("legacy pending sends migrate onto the child checkpoint", async () => {
    const threadIdentifier = `thread-${uuid6(-3)}`;

    let currentConfig: RunnableConfig = {
      configurable: {
        thread_id: threadIdentifier,
        checkpoint_ns: "",
      },
    };

    const parentCheckpointIdentifier = uuid6(0);
    const parentCheckpoint: Checkpoint = {
      v: 1,
      id: parentCheckpointIdentifier,
      ts: "2024-04-19T17:19:07.952Z",
      channel_values: {},
      channel_versions: {},
      versions_seen: {},
    };

    currentConfig = await saver.put(
      currentConfig,
      parentCheckpoint,
      { source: "loop", step: 0, parents: {} },
      {}
    );

    await saver.putWrites(
      currentConfig,
      [
        [TASKS, "send-1"],
        [TASKS, "send-2"],
      ],
      "task-1"
    );
    await saver.putWrites(currentConfig, [[TASKS, "send-3"]], "task-2");

    const parentTuple = await saver.getTuple(currentConfig);
    expect(parentTuple?.checkpoint.channel_values[TASKS]).toBeUndefined();

    const childCheckpointIdentifier = uuid6(1);
    const childCheckpoint: Checkpoint = {
      v: 1,
      id: childCheckpointIdentifier,
      ts: "2024-04-19T17:19:08.952Z",
      channel_values: { state: "ready" },
      channel_versions: { state: 1 },
      versions_seen: {},
    };

    const childConfig = await saver.put(
      currentConfig,
      childCheckpoint,
      { source: "loop", step: 1, parents: {} },
      { state: 1 }
    );

    const childTuple = await saver.getTuple(childConfig);

    expect(childTuple).toBeDefined();
    expect(childTuple?.checkpoint.channel_values[TASKS]).toEqual([
      "send-1",
      "send-2",
      "send-3",
    ]);
    expect(childTuple?.checkpoint.channel_versions[TASKS]).toBeDefined();
  });
});
