import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { configDefaults } from "vitest/config";
import path from "path";

export default defineConfig({
  // ``dist/`` is never this project's output (the bundle goes to ``build.outDir``); a stale one left by an
  // older build would otherwise have vitest collect the compiled copy of every test beside its source.
  test: {
    exclude: [...configDefaults.exclude, "dist/**"],
  },
  plugins: [tailwindcss()],
  root: ".",
  resolve: {
    alias: {
      // The Imbue Studio embed contract, which the page's "Report a bug" sends through (the shell relays it to the
      // chrome), fetched from the mngr commit pyproject.toml pins as the shell's and the chat's are.
      "@minds/embed-contract": path.resolve(
        __dirname,
        "../../../vendor/mngr-assets/apps/minds/imbue/minds/desktop_client/static/embed_contract.js",
      ),
    },
  },
  build: {
    // Inside the Python package, where the app serves it from.
    outDir: path.resolve(__dirname, "../src/getting_started/static"),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": { target: "http://localhost:8030" },
    },
  },
});
