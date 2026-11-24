// Native modules without a JS implementation in Jest.
jest.mock("@react-native-async-storage/async-storage", () =>
  jest.requireActual(
    "@react-native-async-storage/async-storage/jest/async-storage-mock",
  ),
);
jest.mock("@react-native-community/netinfo", () =>
  jest.requireActual("@react-native-community/netinfo/jest/netinfo-mock.js"),
);

// Constants.expoConfig as the app sees it at runtime: evaluated from the real
// app.config.ts (with the test process env, i.e. the development defaults).
jest.mock("expo-constants", () => {
  const actual = jest.requireActual("expo-constants");
  const appConfig = jest.requireActual("./app.config").default;
  const expoConfig = appConfig({ config: {} });
  return {
    ...actual,
    __esModule: true,
    default: { ...actual.default, expoConfig },
  };
});
