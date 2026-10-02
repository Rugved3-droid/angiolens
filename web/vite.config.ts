import { defineConfig } from "vite";

export default defineConfig({
  server: { port: 5178, strictPort: true },
  build: { rollupOptions: { input: { main: "index.html", anatomy: "anatomy.html", atlas: "atlas.html" } } },
  test: { include: ["tests/**/*.test.ts"] },
} as any);
