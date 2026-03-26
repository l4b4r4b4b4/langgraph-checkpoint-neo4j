/**
 * Node/Vitest upstream validation suite for Neo4jSaver.
 *
 * This runs the official @langchain/langgraph-checkpoint-validation tests
 * under Vitest (Node runtime), which matches the upstream expectation for
 * assertion behavior such as `expect(...).rejects` and `expect.soft(...)`.
 *
 * Configure Neo4j via environment variables:
 * - NEO4J_URI (default: bolt://localhost:7687)
 * - NEO4J_USER (default: neo4j)
 * - NEO4J_PASSWORD (default: password)
 */

import {
  validate,
  type CheckpointSaverTestInitializer,
} from "@langchain/langgraph-checkpoint-validation";
import { Neo4jSaver } from "../src/index.js";

const NEO4J_URI = process.env.NEO4J_URI ?? "bolt://localhost:7687";
const NEO4J_USER = process.env.NEO4J_USER ?? "neo4j";
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD ?? "password";

const initializer: CheckpointSaverTestInitializer<Neo4jSaver> = {
  checkpointerName: "Neo4jSaver",
  beforeAllTimeout: 30_000,

  async beforeAll() {
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
    const session = saver.driver.session();
    try {
      await session.run(
        "MATCH (node) WHERE node:Checkpoint OR node:CheckpointBlob OR node:CheckpointWrite DETACH DELETE node"
      );
    } finally {
      await session.close();
    }
    await saver.close();
  },
};

validate(initializer);
