import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src/sw",
      filename: "sw.ts",
      injectRegister: "script",
      registerType: "autoUpdate",
      injectManifest: { injectionPoint: undefined },
      manifest: {
        name: "Casero",
        short_name: "Casero",
        description: "Tus alquileres: quién te debe, cobros por WhatsApp y tus formularios del mes.",
        lang: "es-PE",
        start_url: "/app",
        scope: "/",
        display: "standalone",
        background_color: "#ffffff",
        theme_color: "#0f5c4d",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
    }),
  ],
  server: {
    fs: {
      allow: [".", "../docs/legal"],
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
  },
});
