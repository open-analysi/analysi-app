/// <reference types="vitest" />
import fs from 'node:fs';

import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig, loadEnv, type Plugin } from 'vite';

/**
 * Generates public/OidcTrustedDomains.js from VITE_OIDC_AUTHORITY.
 *
 * OidcTrustedDomains.js runs in the ServiceWorker context where Vite env-var
 * substitution is not available (public/ files are copied verbatim). This plugin
 * writes the file at build-start time so the IdP origin is always derived from
 * the env var rather than hardcoded, making the same build artefact work for
 * any Keycloak deployment.
 */
function generateOidcTrustedDomains(authority: string): Plugin {
  return {
    name: 'generate-oidc-trusted-domains',
    buildStart() {
      let idpOrigin: string;
      try {
        idpOrigin = new URL(authority).origin;
      } catch {
        idpOrigin = 'http://localhost:8080';
      }

      const content = [
        '// Auto-generated from VITE_OIDC_AUTHORITY — do not edit.',
        '// See vite.config.ts generateOidcTrustedDomains plugin.',
        '// eslint-disable-next-line @typescript-eslint/no-unused-vars',
        'const trustedDomains = {',
        '  default: {',
        `    oidcDomains: ['${idpOrigin}', 'http://localhost:8080'],`,
        "    accessTokenDomains: [self.location.origin, 'http://localhost:8001'],",
        '    showAccessToken: true,',
        '  },',
        '};',
        '',
      ].join('\n');

      fs.writeFileSync(
        path.resolve(__dirname, 'public', 'OidcTrustedDomains.js'),
        content,
        'utf-8'
      );
    },
  };
}

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '');

  const oidcAuthority = env.VITE_OIDC_AUTHORITY ?? 'http://localhost:8080/realms/analysi';
  const oidcProxyTarget = env.VITE_OIDC_PROXY_TARGET || 'http://127.0.0.1:8080';

  return {
    plugins: [react(), generateOidcTrustedDomains(oidcAuthority)],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
        '@mocks': path.resolve(__dirname, './mocks'),
        // Use moment-timezone's light build to avoid large JSON files
        'moment-timezone': 'moment-timezone/builds/moment-timezone-with-data-10-year-range.min.js',
      },
    },
    build: {
      commonjsOptions: {
        transformMixedEsModules: true,
      },
    },
    server: {
      proxy: {
        '/api': {
          // Use env var for Docker, fallback to localhost for local dev
          target: env.VITE_BACKEND_API_URL || 'http://localhost:8001',
          changeOrigin: true,
          // The tenant_id is now embedded in the URL by apiClient.ts (from authStore).
          // The proxy just strips the /api prefix: /api/v1/{tenant}/... → /v1/{tenant}/...
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        // Proxy Keycloak through Vite so the OIDC token exchange is same-origin.
        // Chrome's Private Network Access blocks cross-port localhost fetches
        // unless the server returns Access-Control-Allow-Private-Network, which
        // Keycloak does not support.
        // Use 127.0.0.1 instead of localhost to avoid Node.js IPv6-first
        // resolution (::1) which causes ECONNREFUSED on some setups.
        '/realms': { target: oidcProxyTarget },
        '/resources': { target: oidcProxyTarget },
      },
    },
    assetsInclude: ['**/*.jpeg', '**/*.jpg', '**/*.png', '**/*.svg', '**/*.json'],
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './vitest.setup.ts',
      include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
      exclude: ['mocks/**/*', 'src/**/*.integration.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
      isolate: true, // Enable test isolation - each test file runs in isolation
      pool: 'forks',
      maxWorkers: 2, // Limit to 2 parallel processes
      maxConcurrency: 5, // Limit concurrent tests per worker
      clearMocks: true, // Clear mock calls and instances between tests
      restoreMocks: true, // Restore mocked modules between tests
      mockReset: true, // Reset mock state between tests
    },
    optimizeDeps: {
      exclude: ['@hpcc-js/wasm'],
    },
  };
});
