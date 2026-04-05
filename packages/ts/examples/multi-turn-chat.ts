/**
 * Multi-turn chat example — Neo4jSaver checkpoint API end-to-end.
 *
 * Demonstrates how the Neo4j checkpointer stores, retrieves, lists, and
 * deletes conversation state across multiple turns.  No LLM required —
 * this example operates directly on the checkpoint API to show exactly
 * what the checkpointer does under the hood.
 *
 * Run with Bun:
 *
 *   NEO4J_URI=bolt://localhost:7387 NEO4J_USER=neo4j NEO4J_PASSWORD=password \
 *     bun run examples/multi-turn-chat.ts
 *
 * Requires a running Neo4j instance (e.g. `bun run neo4j:up` from repo root).
 *
 * @packageDocumentation
 */

import { Neo4jSaver } from "../src/index.js";
import {
  emptyCheckpoint,
  uuid6,
  type Checkpoint,
  type CheckpointMetadata,
  type CheckpointTuple,
  type ChannelVersions,
} from "@langchain/langgraph-checkpoint";
import type { RunnableConfig } from "@langchain/core/runnables";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const NEO4J_URI = process.env.NEO4J_URI ?? "bolt://localhost:7387";
const NEO4J_USER = process.env.NEO4J_USER ?? "neo4j";
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD ?? "password";
const THREAD_ID = "ts-multi-turn-demo";

// ---------------------------------------------------------------------------
// Simulated chat helpers
// ---------------------------------------------------------------------------

interface Message {
  role: "user" | "assistant";
  content: string;
}

/**
 * Fake chatbot: echoes user input with a turn counter.
 * Recognises simple math expressions and "evaluates" them.
 */
function fakeReply(userText: string, turnCount: number): string {
  const mathMatch = userText.match(/(\d+(?:\.\d+)?\s*[+\-*/]\s*\d+(?:\.\d+)?)/);
  if (mathMatch) {
    const expression = mathMatch[1];
    // Safe-ish eval for simple arithmetic only
    const result = Function(`"use strict"; return (${expression})`)();
    return `Calculator: ${expression} = ${result}`;
  }
  return `[Turn ${turnCount}] You said: ${userText}`;
}

// ---------------------------------------------------------------------------
// Chat turn — put a checkpoint after each user+assistant exchange
// ---------------------------------------------------------------------------

/**
 * Simulate a single chat turn: append user + assistant messages, bump
 * channel versions, and persist via the checkpointer.
 *
 * Uses `emptyCheckpoint()` and `uuid6()` from the upstream checkpoint SDK
 * so that checkpoint IDs are time-sorted (required for correct ordering
 * in `list()` and `getTuple()` without explicit checkpoint_id).
 */
async function chatTurn(
  saver: Neo4jSaver,
  threadId: string,
  checkpointNs: string,
  previousConfig: RunnableConfig | null,
  previousCheckpoint: Checkpoint | null,
  userText: string,
  turnCount: number,
): Promise<{
  config: RunnableConfig;
  checkpoint: Checkpoint;
}> {
  const assistantText = fakeReply(userText, turnCount);

  // Build message list — append to existing or start fresh
  const existingMessages: Message[] = previousCheckpoint
    ? ((previousCheckpoint.channel_values as Record<string, unknown>)
        ?.messages as Message[]) ?? []
    : [];
  const newMessages: Message[] = [
    ...existingMessages,
    { role: "user", content: userText },
    { role: "assistant", content: assistantText },
  ];

  // Determine previous channel version for messages
  const previousVersions: Record<string, number> = previousCheckpoint
    ? (previousCheckpoint.channel_versions as Record<string, number>) ?? {}
    : {};
  const messagesVersion = saver.getNextVersion(
    previousVersions.messages ?? null,
    null as unknown,
  ) as number;
  const turnCountVersion = saver.getNextVersion(
    previousVersions.turn_count ?? null,
    null as unknown,
  ) as number;

  // Build the new checkpoint using the SDK's emptyCheckpoint as a base,
  // then override with our data.  uuid6() produces time-sorted IDs that
  // the "ORDER BY checkpoint_id DESC" queries rely on.
  const base = emptyCheckpoint();
  const checkpoint: Checkpoint = {
    ...base,
    id: uuid6(turnCount),
    ts: new Date().toISOString(),
    channel_values: {
      messages: newMessages,
      turn_count: turnCount,
    },
    channel_versions: {
      messages: messagesVersion,
      turn_count: turnCountVersion,
    },
  };

  const newVersions: ChannelVersions = {
    messages: messagesVersion,
    turn_count: turnCountVersion,
  };

  // Config pointing to the parent checkpoint (if any)
  const config: RunnableConfig = {
    configurable: {
      thread_id: threadId,
      checkpoint_ns: checkpointNs,
      ...(previousConfig?.configurable
        ? { checkpoint_id: previousConfig.configurable.checkpoint_id }
        : {}),
    },
  };

  // Store the checkpoint
  const metadata: CheckpointMetadata = {
    source: previousConfig ? "loop" : "input",
    step: turnCount,
    writes: { messages: [{ role: "user", content: userText }] },
  } as unknown as CheckpointMetadata;

  const storedConfig = await saver.put(config, checkpoint, metadata, newVersions);

  console.log(`  >>> User: ${userText}`);
  console.log(`  <<< Bot:  ${assistantText}`);
  console.log(`      (turn ${turnCount}, checkpoint ${checkpoint.id.slice(0, 16)}...)`);

  return { config: storedConfig, checkpoint };
}

// ---------------------------------------------------------------------------
// Main demo
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log("Neo4j URI:    ", NEO4J_URI);
  console.log("Neo4j User:   ", NEO4J_USER);
  console.log("Thread ID:    ", THREAD_ID);
  console.log();

  const saver = Neo4jSaver.fromConnString(NEO4J_URI, {
    username: NEO4J_USER,
    password: NEO4J_PASSWORD,
  });

  try {
    // -----------------------------------------------------------------------
    // 1. Setup (idempotent)
    // -----------------------------------------------------------------------
    await saver.setup();
    console.log("Schema setup complete (idempotent).\n");

    // Clean start for demo repeatability
    await saver.deleteThread(THREAD_ID);

    // -----------------------------------------------------------------------
    // 2. Multi-turn conversation
    // -----------------------------------------------------------------------
    console.log("=".repeat(60));
    console.log("  MULTI-TURN CONVERSATION");
    console.log("=".repeat(60));
    console.log();

    const userMessages = [
      "Hello, Neo4j checkpointer!",
      "What is 42 + 17?",
      "Remember me across restarts!",
    ];

    let previousConfig: RunnableConfig | null = null;
    let previousCheckpoint: Checkpoint | null = null;

    for (let turn = 0; turn < userMessages.length; turn++) {
      const result = await chatTurn(
        saver,
        THREAD_ID,
        "",
        previousConfig,
        previousCheckpoint,
        userMessages[turn],
        turn + 1,
      );
      previousConfig = result.config;
      previousCheckpoint = result.checkpoint;
      console.log();
    }

    // -----------------------------------------------------------------------
    // 3. Retrieve latest checkpoint
    // -----------------------------------------------------------------------
    console.log("=".repeat(60));
    console.log("  RETRIEVE LATEST STATE");
    console.log("=".repeat(60));
    console.log();

    const latestTuple = await saver.getTuple({
      configurable: { thread_id: THREAD_ID, checkpoint_ns: "" },
    });

    if (latestTuple) {
      const channelValues = latestTuple.checkpoint.channel_values as Record<
        string,
        unknown
      >;
      const messages = (channelValues?.messages ?? []) as Message[];
      console.log(`  Checkpoint ID:   ${latestTuple.config.configurable?.checkpoint_id}`);
      console.log(`  Turn count:      ${channelValues?.turn_count}`);
      console.log(`  Total messages:  ${messages.length}`);
      console.log(`  Metadata source: ${(latestTuple.metadata as Record<string, unknown>)?.source}`);
      console.log(`  Metadata step:   ${(latestTuple.metadata as Record<string, unknown>)?.step}`);
      console.log();
      console.log("  Messages:");
      for (const msg of messages) {
        console.log(`    [${msg.role}] ${msg.content}`);
      }
    } else {
      console.log("  ERROR: No checkpoint found!");
    }
    console.log();

    // -----------------------------------------------------------------------
    // 4. List checkpoint history
    // -----------------------------------------------------------------------
    console.log("=".repeat(60));
    console.log("  CHECKPOINT HISTORY");
    console.log("=".repeat(60));
    console.log();

    const allCheckpoints: CheckpointTuple[] = [];
    for await (const tuple of saver.list({
      configurable: { thread_id: THREAD_ID, checkpoint_ns: "" },
    })) {
      allCheckpoints.push(tuple);
    }

    console.log(`  Total checkpoints: ${allCheckpoints.length}`);
    for (let index = 0; index < allCheckpoints.length; index++) {
      const tuple = allCheckpoints[index]!;
      const checkpointId = tuple.config.configurable?.checkpoint_id?.slice(0, 16);
      const step = (tuple.metadata as Record<string, unknown>)?.step ?? "?";
      const source = (tuple.metadata as Record<string, unknown>)?.source ?? "?";
      console.log(`    [${index}] id=${checkpointId}...  source=${source}  step=${step}`);
    }
    console.log();

    // -----------------------------------------------------------------------
    // 5. Time travel — read state after just the first turn
    // -----------------------------------------------------------------------
    console.log("=".repeat(60));
    console.log("  TIME TRAVEL");
    console.log("=".repeat(60));
    console.log();

    if (allCheckpoints.length >= 2) {
      // List is newest-first, so the last entry is the earliest checkpoint
      const earliest = allCheckpoints[allCheckpoints.length - 1]!;
      const earlyId = earliest.config.configurable?.checkpoint_id;

      const earlyTuple = await saver.getTuple({
        configurable: {
          thread_id: THREAD_ID,
          checkpoint_ns: "",
          checkpoint_id: earlyId,
        },
      });

      if (earlyTuple) {
        const channelValues = earlyTuple.checkpoint.channel_values as Record<
          string,
          unknown
        >;
        const messages = (channelValues?.messages ?? []) as Message[];
        console.log(`  Travelled to checkpoint ${earlyId?.slice(0, 16)}...`);
        console.log(`  Messages at that point: ${messages.length}`);
        for (const msg of messages) {
          console.log(`    [${msg.role}] ${msg.content}`);
        }
      }
    } else {
      console.log("  (Not enough checkpoints for time travel demo)");
    }
    console.log();

    // -----------------------------------------------------------------------
    // 6. Pending writes demo
    // -----------------------------------------------------------------------
    console.log("=".repeat(60));
    console.log("  PENDING WRITES");
    console.log("=".repeat(60));
    console.log();

    if (previousConfig) {
      await saver.putWrites(
        previousConfig,
        [
          ["draft_reply", "I'm thinking about Neo4j..."],
          ["tool_result", { tool: "calculator", result: 59 }],
        ],
        "pending-task-1",
      );
      console.log("  Stored 2 pending writes.");

      const withWrites = await saver.getTuple(previousConfig);
      if (withWrites && withWrites.pendingWrites) {
        console.log(`  Retrieved ${withWrites.pendingWrites.length} pending writes:`);
        for (const pendingWrite of withWrites.pendingWrites) {
          const [taskId, channel, value] = pendingWrite as [string, string, unknown];
          console.log(`    task=${taskId}  channel=${channel}  value=${JSON.stringify(value)}`);
        }
      }
    }
    console.log();

    // -----------------------------------------------------------------------
    // 7. Persistence proof — close and reopen
    // -----------------------------------------------------------------------
    console.log("=".repeat(60));
    console.log("  PERSISTENCE PROOF: close → reopen → verify");
    console.log("=".repeat(60));
    console.log();

    // Close the current saver
    await saver.close();
    console.log("  Connection closed.");

    // Open a brand new saver
    const saver2 = Neo4jSaver.fromConnString(NEO4J_URI, {
      username: NEO4J_USER,
      password: NEO4J_PASSWORD,
    });

    try {
      await saver2.setup();
      console.log("  Reopened with new connection.\n");

      const restored = await saver2.getTuple({
        configurable: { thread_id: THREAD_ID, checkpoint_ns: "" },
      });

      if (restored) {
        const channelValues = restored.checkpoint.channel_values as Record<
          string,
          unknown
        >;
        const messages = (channelValues?.messages ?? []) as Message[];
        console.log(`  ✓ Restored ${messages.length} messages from Neo4j:`);
        for (const msg of messages) {
          console.log(`    [${msg.role}] ${msg.content}`);
        }
      } else {
        console.log("  ✗ ERROR: No state found! Persistence is broken.");
      }
      console.log();

      // -------------------------------------------------------------------
      // 8. Cleanup
      // -------------------------------------------------------------------
      console.log("=".repeat(60));
      console.log("  CLEANUP");
      console.log("=".repeat(60));
      console.log();

      await saver2.deleteThread(THREAD_ID);
      console.log(`  Thread '${THREAD_ID}' deleted.`);

      // Verify deletion
      const deleted = await saver2.getTuple({
        configurable: { thread_id: THREAD_ID, checkpoint_ns: "" },
      });
      console.log(
        `  Verification: getTuple returns ${deleted === undefined ? "undefined ✓" : "something ✗"}`,
      );
      console.log();

      console.log("=".repeat(60));
      console.log("  All demos complete!");
      console.log("=".repeat(60));
    } finally {
      await saver2.close();
    }
  } catch (error) {
    // If saver is still open, close it
    try {
      await saver.close();
    } catch {
      // ignore — may already be closed
    }
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

main().catch((error) => {
  console.error("Demo failed:", error);
  process.exit(1);
});
