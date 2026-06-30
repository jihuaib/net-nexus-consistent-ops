import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

const backendTarget = process.env.VITE_PROXY_TARGET || process.env.VITE_API_BASE || 'http://127.0.0.1:8010';

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  server:
    command === 'serve'
      ? {
          proxy: {
            '/api': {
              target: backendTarget,
              changeOrigin: true,
              ws: true,
            },
          },
        }
      : undefined,
  preview: {
    host: '0.0.0.0',
    port: 4178,
  },
  build: {
    sourcemap: false,
  },
  resolve: {
    dedupe: ['vue'],
    alias: {
      vue: fileURLToPath(new URL('./node_modules/vue/dist/vue.runtime.esm-bundler.js', import.meta.url)),
    },
  },
}));
