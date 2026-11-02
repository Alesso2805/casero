import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The panel's own bundle, served by the API on its loopback port: none of it reaches the public
// site (ADR-0008).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/admin/",
  publicDir: false,
  build: {
    outDir: "dist-admin",
    rollupOptions: { input: "admin.html" },
  },
});
