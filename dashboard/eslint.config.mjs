import nextConfig from "eslint-config-next";

/** @type {import('eslint').Linter.Config[]} */
const config = [
  ...nextConfig,
  {
    rules: {
      // set-state-in-effect fires on valid async/conditional setState patterns
      // (e.g. void fetchData(), conditional tab switches on status change).
      // Downgrade to warn — these are deliberate patterns, not bugs.
      "react-hooks/set-state-in-effect": "warn",
      // no-anonymous-default-export doesn't apply to config files
      "import/no-anonymous-default-export": "off",
    },
  },
  {
    ignores: [".next/**", "node_modules/**", "out/**"],
  },
];

export default config;
