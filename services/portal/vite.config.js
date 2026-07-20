import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const base = process.env.VITE_BASE_PATH || "/";

export default defineConfig({
  plugins: [react()],
  base,
  server: {
    port: 5173,
    proxy: {
      "/config.json": { target: "http://127.0.0.1:5173", bypass: () => false },
    },
  },
});
