import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8000', ws: true }, '/health': 'http://127.0.0.1:8000' } },
  build: { rollupOptions: { output: { manualChunks: { player: ['hls.js/dist/hls.light.mjs'], react: ['react', 'react-dom', 'react-router-dom'] } } } },
});
