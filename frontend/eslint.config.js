import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // V2-LLD-010 §15.3 — forme exécutable de deux décisions de sécurité du LLD. Une
      // décision qui ne repose que sur la relecture est une décision qui sera annulée par
      // mégarde.
      'no-restricted-globals': [
        'error',
        {
          name: 'localStorage',
          message:
            'localStorage est écarté (§4.2) : il survit à la fermeture du navigateur et transforme une faille XSS en vol de session de trente jours. Utilisez sessionStorage, ou la mémoire du module pour le jeton d\'accès.',
        },
      ],
      'no-restricted-properties': [
        'error',
        {
          object: 'window',
          property: 'localStorage',
          message: 'localStorage est écarté (V2-LLD-010 §4.2).',
        },
      ],
      'react/no-danger': 'off',
      'no-restricted-syntax': [
        'error',
        {
          selector: 'JSXAttribute[name.name="dangerouslySetInnerHTML"]',
          message:
            'dangerouslySetInnerHTML réintroduit la surface XSS que §12.3 ferme en rendant le markdown sans rehype-raw.',
        },
      ],
    },
  },
])
