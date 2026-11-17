import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: {
    alias: { "@": __dirname },
  },
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts", "app/api/**/*.test.ts"],
  },
})
