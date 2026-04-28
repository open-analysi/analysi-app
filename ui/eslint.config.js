import js from '@eslint/js';
import typescript from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import importPlugin from 'eslint-plugin-import';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import sonarjs from 'eslint-plugin-sonarjs';
import unicorn from 'eslint-plugin-unicorn';
import globals from 'globals';

export default [
  // Base config for all files
  {
    ignores: [
      'dist/**',
      'build/**',
      'node_modules/**',
      'src/generated/**',
      'coverage/**',
      'playwright-report/**',
      'public/**/*.js',
      'scripts/**',
      'demo/**',
      '*.config.js',
      '*.config.ts',
      'vite.config.ts',
      'vite-env.d.ts',
    ],
  },

  // JavaScript base config
  js.configs.recommended,

  // Main config for TypeScript and React files
  {
    files: ['**/*.{ts,tsx,js,jsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: {
          jsx: true,
        },
        project: ['./tsconfig.json', './tsconfig.node.json'],
      },
      globals: {
        ...globals.browser,
        ...globals.es2021,
        ...globals.node,
      },
    },
    plugins: {
      '@typescript-eslint': typescript,
      react,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
      sonarjs,
      unicorn,
      import: importPlugin,
    },
    settings: {
      react: {
        version: 'detect',
      },
      'import/resolver': {
        typescript: {},
        node: {
          extensions: ['.js', '.jsx', '.ts', '.tsx', '.svg'],
          moduleDirectory: ['node_modules', 'src/'],
          paths: ['./node_modules'],
        },
      },
    },
    rules: {
      // TypeScript recommended rules
      ...typescript.configs.recommended.rules,
      ...typescript.configs['recommended-type-checked'].rules,

      // React recommended rules
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,

      // JSX a11y recommended rules
      ...jsxA11y.configs.recommended.rules,

      // SonarJS recommended rules
      ...sonarjs.configs.recommended.rules,

      // Unicorn recommended rules (selectively - it has many rules)
      'unicorn/prevent-abbreviations': 'off',
      'unicorn/filename-case': [
        'error',
        {
          cases: {
            camelCase: true,
            pascalCase: true,
          },
        },
      ],
      'unicorn/prefer-query-selector': 'off',

      // Import rules
      ...importPlugin.configs.recommended.rules,
      ...importPlugin.configs.typescript.rules,
      'import/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          pathGroups: [
            {
              pattern: 'react',
              group: 'external',
              position: 'before',
            },
          ],
          pathGroupsExcludedImportTypes: ['react'],
          'newlines-between': 'always',
          alphabetize: {
            order: 'asc',
            caseInsensitive: true,
          },
        },
      ],
      'import/no-named-as-default': 'off',
      'import/no-named-as-default-member': 'off',
      'import/default': 'off',
      'import/no-unresolved': [
        'error',
        {
          ignore: ['^msw'],
        },
      ],

      // Custom React rules
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',

      // Custom TypeScript rules
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-unsafe-call': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-argument': 'error',
      '@typescript-eslint/no-explicit-any': [
        'error',
        {
          ignoreRestArgs: true,
        },
      ],
      '@typescript-eslint/no-floating-promises': [
        'error',
        {
          ignoreVoid: true,
          ignoreIIFE: true,
        },
      ],
      '@typescript-eslint/no-unsafe-return': 'error',

      // Custom SonarJS rules
      'sonarjs/cognitive-complexity': ['error', 15],
      'sonarjs/no-duplicate-string': ['error', { threshold: 5 }],

      // Console rules
      'no-console': [
        'warn',
        {
          allow: ['warn', 'error', 'info'],
        },
      ],
    },
  },

  // Test files config - relax some rules
  {
    files: ['**/__tests__/**/*.[jt]s?(x)', '**/?(*.)+(spec|test).[jt]s?(x)'],
    rules: {
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      // Test fixtures legitimately repeat literals (endpoint URLs, sample
      // payloads, expected message strings) and stringify mock objects with
      // structural assertions. Extracting constants per case fights the
      // self-contained "given/when/then" shape of each test.
      'sonarjs/no-duplicate-string': 'off',
      '@typescript-eslint/no-base-to-string': 'off',
      // vi.mocked(x.method) is the canonical vitest mock pattern but reads
      // as an unbound method to the lint rule.
      '@typescript-eslint/unbound-method': 'off',
      // Test fixtures often use nested ternaries to coerce mock arg types
      // (e.g., URL | string | Request); refactoring each into named locals
      // bloats the test without changing behaviour.
      'sonarjs/no-nested-conditional': 'off',
    },
  },

  // Test setup files config
  {
    files: ['**/test/setup.ts', 'vitest.setup.ts'],
    rules: {
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },

  // Mock files config
  {
    files: ['mocks/**/*'],
    rules: {
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
    },
  },

  // Visualization components - third-party library type gaps (Reaflow, Cytoscape)
  {
    files: [
      'src/components/workflows/Workflow*.tsx',
      'src/components/workflows/WorkflowExecution*.tsx',
      'src/components/settings/KnowledgeGraph*.tsx',
      'src/components/settings/graph/*.tsx',
    ],
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn', // Downgrade to warning for library type assertions
      '@typescript-eslint/no-unsafe-assignment': 'warn',
      '@typescript-eslint/no-unsafe-member-access': 'warn',
      '@typescript-eslint/no-unsafe-call': 'warn',
      '@typescript-eslint/no-unsafe-return': 'warn',
      '@typescript-eslint/no-unsafe-argument': 'warn',
    },
  },

  // Backend API service - dynamic response types
  {
    files: ['src/services/backendApi.ts', 'src/services/api.ts'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unsafe-assignment': 'warn',
      '@typescript-eslint/no-unsafe-member-access': 'warn',
      '@typescript-eslint/no-unsafe-return': 'warn',
      '@typescript-eslint/no-unsafe-argument': 'warn',
    },
  },

  // Type definition files - extensibility
  {
    files: ['src/types/*.ts'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
];
