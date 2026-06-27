import { defineConfig } from "vite";

// The static front-end lives in `site/`. Generated data and static assets are
// in `site/public/` (served at the web root by Vite, in both dev and build).
export default defineConfig({
  root: "site",
  publicDir: "public",
  server: {
    port: 5173,
    strictPort: false,
    open: false,
  },
  preview: {
    port: 4173,
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
