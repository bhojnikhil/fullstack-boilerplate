// Shared ESLint flat config for Next.js apps.
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default [
  ...nextVitals,
  ...nextTypeScript,
  { ignores: ["playwright-report/**", "test-results/**"] },
];
