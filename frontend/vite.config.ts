import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "FlashCloset",
        short_name: "FlashCloset",
        description: "Tu clóset real, convertido en juego de vestir.",
        lang: "es",
        start_url: "/",
        display: "standalone",
        background_color: "#2b1150",
        theme_color: "#5a2196",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          // Android crops icons to its own shape; the maskable one keeps its art
          // inside the safe zone so nothing important gets cut off.
          {
            src: "/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    host: "127.0.0.1",
  },
});
