import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextVitals,
  { ignores: [".next/**", "node_modules/**"] },
  { rules: { "@typescript-eslint/no-explicit-any": "off", "react-hooks/exhaustive-deps": "warn", "react-hooks/set-state-in-effect": "warn", "react-hooks/immutability": "warn", "react-hooks/refs": "warn", "@next/next/no-img-element": "off" } },
];
export default config;
