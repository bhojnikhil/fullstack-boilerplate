/** @type {import('jest').Config} */
module.exports = {
  preset: "jest-expo",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  // pnpm variant from https://docs.expo.dev/develop/unit-testing/, plus
  // standard-navigation (ESM-only dependency of expo-router 58).
  transformIgnorePatterns: [
    "node_modules/(?!(.pnpm|(jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg|standard-navigation))",
  ],
  testPathIgnorePatterns: ["/node_modules/", "/.expo/"],
};
