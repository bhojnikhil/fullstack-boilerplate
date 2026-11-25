import { APP_CONFIG_ENV_KEYS } from "./app.config";

// Tests must not depend on the developer's shell: a release-style
// APP_VARIANT/API_URL (or EAS markers) exported there would otherwise change
// what app.config.ts produces. Jest gives each test file its own process.env.
for (const key of APP_CONFIG_ENV_KEYS) delete process.env[key];

// Native modules without a JS implementation in Jest.
jest.mock("@react-native-async-storage/async-storage", () =>
  jest.requireActual(
    "@react-native-async-storage/async-storage/jest/async-storage-mock",
  ),
);
jest.mock("@react-native-community/netinfo", () =>
  jest.requireActual("@react-native-community/netinfo/jest/netinfo-mock.js"),
);

// The Sentry native SDK has no JS implementation in Jest (and ships ESM).
jest.mock("@sentry/react-native", () => ({ init: jest.fn() }));

// Constants.expoConfig as the app sees it at runtime: the real app.config.ts
// evaluated with an explicitly clean environment (the development defaults).
jest.mock("expo-constants", () => {
  const actual = jest.requireActual("expo-constants");
  const { default: appConfig, withoutAppConfigEnv } =
    jest.requireActual("./app.config");
  const saved = process.env;
  process.env = withoutAppConfigEnv(saved);
  try {
    const expoConfig = appConfig({ config: {} });
    return {
      ...actual,
      __esModule: true,
      default: { ...actual.default, expoConfig },
    };
  } finally {
    process.env = saved;
  }
});
