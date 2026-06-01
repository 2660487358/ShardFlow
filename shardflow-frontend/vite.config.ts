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
