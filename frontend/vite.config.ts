import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";

// The Python server serves dist/ in production. In `vite` dev mode the API
// lives on the Python server, so the dev server forwards /api to it.
const devApiServer = "http://localhost:8080";

export default defineConfig({
  plugins: [tailwindcss()],
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: { "/api": devApiServer } },
  test: {
    // DOM tests opt in with `// @vitest-environment jsdom` (ADR-06).
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
