import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { configDefaults } from "vitest/config";
import path from "path";

// Where the real chat backend lives (agent discovery, message send/receive).
// See README.md -- this fork carries no chat backend of its own, so point it
// at any backend that implements the same /api contract.
const CHAT_BACKEND_URL = process.env.CHAT_BACKEND_URL ?? "http://localhost:8000";
// The companion control-plane backend in ../control-backend.
const CONTROL_BACKEND_URL = process.env.CONTROL_BACKEND_URL ?? "http://localhost:8082";

export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, "dist/**"],
  },
  plugins: [tailwindcss()],
  publicDir: "media",
  root: ".",
  build: {
    outDir: path.resolve(__dirname, "dist"),
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    port: 8080,
    strictPort: true,
    // Set to a specific list of hostnames (or remove this line) if you are
    // reverse-proxying this dev server behind something that rewrites the
    // Host header; see Vite's server.allowedHosts docs.
    allowedHosts: true,
    proxy: {
      "/api": {
        target: CHAT_BACKEND_URL,
        ws: true,
      },
      // Path is stripped since the control backend serves /ws and
      // /select-agent at its own root.
      "/control": {
        target: CONTROL_BACKEND_URL,
        ws: true,
        rewrite: (path) => path.replace(/^\/control/, ""),
      },
    },
  },
});
