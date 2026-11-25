// Shared ESLint flat config for Expo (React Native) apps.
//
// eslint-config-expo ships a flat config (eslint-config-expo/flat). Resolution
// happens from this package, which owns the eslint-config-expo dependency.
import expoConfig from "eslint-config-expo/flat.js";

/** @type {import("eslint").Linter.Config[]} */
const config = [
  {
    ignores: [
      ".expo/**",
      "android/**",
      "ios/**",
      "dist/**",
      "coverage/**",
      "node_modules/**",
      "expo-env.d.ts",
    ],
  },
  ...expoConfig,
];

export default config;
