import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: ["tests/**/*.vitest.ts", "packages/ts/tests/**/*.vitest.ts"],
    exclude: ["node_modules", "dist"],
    testTimeout: 60_000,
    hookTimeout: 60_000,
    isolate: true,
    reporters: ["default"],
  },
});
