import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Em desenvolvimento, /api vai para o backend FastAPI (backend/).
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
