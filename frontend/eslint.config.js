import js from "@eslint/js";
import globals from "globals";
import vue from "eslint-plugin-vue";

export default [
  { ignores: ["dist/**", "node_modules/**", ".zcode/**"] },
  js.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: {
        scriptHonorNoTemplate: false,
      },
    },
  },
  {
    languageOptions: {
      globals: { ...globals.browser },
      ecmaVersion: "latest",
      sourceType: "module",
    },
  },
  {
    rules: {
      "vue/multi-word-component-names": "off",
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      // The only v-html site renders MarkdownIt output configured with
      // html: false, so raw HTML in source text is escaped before injection.
      "vue/no-v-html": "off",
    },
  },
  // Browser tests run in vitest's node process and use its globals.
  {
    files: ["**/*.test.js"],
    languageOptions: { globals: { ...globals.node } },
  },
];
