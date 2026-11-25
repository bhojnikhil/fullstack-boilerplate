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

// Native modules that have no JS implementation in Jest. Tests that care about
// their behavior override these with their own jest.mock / mockImplementation.
jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  getPermissionsAsync: jest.fn(async () => ({
    status: "undetermined",
    canAskAgain: true,
  })),
  requestPermissionsAsync: jest.fn(async () => ({ status: "denied" })),
  setNotificationChannelAsync: jest.fn(async () => undefined),
  getExpoPushTokenAsync: jest.fn(async () => ({ data: "ExponentPushToken[test]" })),
  getLastNotificationResponseAsync: jest.fn(async () => null),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  AndroidImportance: { DEFAULT: 3 },
}));
jest.mock("expo-local-authentication", () => ({
  hasHardwareAsync: jest.fn(async () => true),
  isEnrolledAsync: jest.fn(async () => true),
  authenticateAsync: jest.fn(async () => ({ success: true })),
}));
jest.mock("expo-device", () => ({
  isDevice: false,
  deviceName: "Test phone",
  modelName: "Test",
}));
jest.mock("expo-secure-store", () => {
  const store = new Map<string, string>();
  return {
    AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY: 1,
    getItemAsync: jest.fn(async (key: string) => store.get(key) ?? null),
    setItemAsync: jest.fn(
      async (key: string, value: string) => void store.set(key, value),
    ),
    deleteItemAsync: jest.fn(async (key: string) => void store.delete(key)),
  };
});
jest.mock("@react-native-google-signin/google-signin", () => {
  throw new Error("native module unavailable (as in Expo Go)");
});
