import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const proxyTarget =
  process.env.VITE_PROXY_TARGET ||
  process.env.VITE_API_BASE_URL ||
  (process.env.DOCKER ? 'http://backend:8000' : 'http://127.0.0.1:8000');

const devServerPort = Number(
  process.env.VITE_DEV_SERVER_PORT || process.env.VITE_PORT || 5173
);

const hmrClientPort = Number(
  process.env.VITE_HMR_CLIENT_PORT || (process.env.DOCKER ? 5174 : devServerPort)
);

const hmrHost = process.env.VITE_HMR_HOST;

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || '/',
  server: {
    host: true,
    strictPort: true,
    port: devServerPort,
    hmr: {
      clientPort: hmrClientPort,
      ...(hmrHost ? { host: hmrHost } : {}),
    },
    // Proxy API calls to backend during development
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/health': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/route': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/graph': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});
