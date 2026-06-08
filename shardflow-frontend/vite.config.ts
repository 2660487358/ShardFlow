import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    server: {
      port: 3000,
      proxy: {
        '/agent/v1': {
          target: env.VITE_SF_AGENT_PROXY || 'http://localhost:8000',
          changeOrigin: true,
          // SSE streaming: disable proxy buffering so chunks arrive immediately
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
                proxyRes.headers['cache-control'] = 'no-cache';
                proxyRes.headers['x-accel-buffering'] = 'no';
              }
            });
          },
        },
        '/auth': {
          target: env.VITE_SF_SYSTEM_PROXY || 'http://localhost:8200',
          changeOrigin: true,
        },
        '/api/v1': {
          target: env.VITE_SF_SYSTEM_PROXY || 'http://localhost:8200',
          changeOrigin: true,
        },
      },
    },
  };
});
