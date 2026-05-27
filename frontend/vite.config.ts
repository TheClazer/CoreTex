import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/convert": "http://localhost:8000",
      "/status": "http://localhost:8000",
      "/download": "http://localhost:8000",
      "/temp": "http://localhost:8000",
      "/auth/providers": "http://localhost:8000",
      "/auth/signup": "http://localhost:8000",
      "/auth/login": "http://localhost:8000",
      "/auth/me": "http://localhost:8000",
      "/auth/google": "http://localhost:8000",
      "/auth/github": "http://localhost:8000",
      "/history": "http://localhost:8000",
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
