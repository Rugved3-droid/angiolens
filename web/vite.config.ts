import { defineConfig } from "vite";

export default defineConfig({
  server: { port: 5178, strictPort: true },
  test: { include: ["tests/**/*.test.ts"] },
} as any);
