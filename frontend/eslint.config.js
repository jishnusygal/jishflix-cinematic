import js from '@eslint/js';
import hooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
export default [
  { ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'] },
  js.configs.recommended,
  { files: ['**/*.{js,jsx}'], languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: {...globals.browser, ...globals.node}, parserOptions: { ecmaFeatures: { jsx: true } } }, plugins: {'react-hooks': hooks}, rules: {...hooks.configs.recommended.rules, 'no-unused-vars': ['error', {varsIgnorePattern: '^[A-Z_]', argsIgnorePattern: '^[A-Z_]'}]} },
];
