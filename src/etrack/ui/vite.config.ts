import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base "./": the canvas is mounted under any prefix (`/etrack/`), so every asset and API path stays relative.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:28130" } },
});
