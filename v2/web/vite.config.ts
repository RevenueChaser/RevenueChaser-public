// The v2 web app builds to `dist/`, which the door serves as static files (ADR decision 6).
// No CDN: every asset is bundled or self-hosted (decision 2).
import { defineConfig } from 'vite';

export default defineConfig({
  // JSX is compiled by Vite's own esbuild transform; @vitejs/plugin-react is Fast Refresh only (ADR decision 4).
  base: './',
  build: { outDir: 'dist', emptyOutDir: true, sourcemap: false },
});
