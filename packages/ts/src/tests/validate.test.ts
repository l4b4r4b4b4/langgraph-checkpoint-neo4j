/**
 * Validation test suite for Neo4jSaver.
 *
 * Uses the official @langchain/langgraph-checkpoint-validation framework
 * to verify that Neo4jSaver correctly implements BaseCheckpointSaver.
 *
 * Requires a running Neo4j instance. Configure via environment variables:
 *   NEO4J_URI      (default: bolt://localhost:7687)
 *   NEO4J_USER     (default: neo4j)
 *   NEO4J_PASSWORD (default: password)
 */

import { validate } from "@langchain/langgraph-checkpoint-validation";
import type { CheckpointSaverTestInitializer } from "@langchain/langgraph-checkpoint-validation";
import { Neo4jSaver } from "../index.js";

const NEO4J_URI = process.env.NEO4J_URI ?? "bolt://localhost:7687";
const NEO4J_USER = process.env.NEO4J_USER ?? "neo4j";
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD ?? "password";

const initializer: CheckpointSaverTestInitializer<Neo4jSaver> = {
  checkpointerName: "Neo4jSaver",

  beforeAllTimeout: 30_000,

  async beforeAll() {
    // Verify Neo4j connectivity by creating and closing a temporary saver.
    const saver = Neo4jSaver.fromConnString(NEO4J_URI, {
      username: NEO4J_USER,
      password: NEO4J_PASSWORD,
    });
    await saver.setup();
    await saver.close();
  },

  async createCheckpointer(): Promise<Neo4jSaver> {
    const saver = Neo4jSaver.fromConnString(NEO4J_URI, {
      username: NEO4J_USER,
      password: NEO4J_PASSWORD,
    });
    await saver.setup();
    return saver;
  },

  async destroyCheckpointer(saver: Neo4jSaver): Promise<void> {
    // Clean up all checkpoint data to ensure test isolation.
    const session = saver.driver.session();
    try {
      await session.run(
        "MATCH (n) WHERE n:Checkpoint OR n:CheckpointBlob OR n:CheckpointWrite DETACH DELETE n"
      );
    } finally {
      await session.close();
    }
    await saver.close();
  },
};

validate(initializer);
