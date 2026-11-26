import { act, render, screen, waitFor } from "@testing-library/react-native";
import * as SecureStore from "expo-secure-store";
import * as LocalAuthentication from "expo-local-authentication";
import { Text } from "react-native";
import { AppLockGate } from "../app-lock";
import { ServicesProvider } from "@/providers/services";
import { makeServices } from "../../../../test-utils/services";

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));
jest.mock("expo-local-authentication", () => ({ authenticateAsync: jest.fn() }));

it("blocks signed-in content while the preference read is pending", async () => {
  let resolve!: (value: string | null) => void;
  jest.mocked(SecureStore.getItemAsync).mockReturnValue(
    new Promise((r) => {
      resolve = r;
    }),
  );
  const { services } = makeServices();
  await services.session.load();
  await render(
    <ServicesProvider services={services}>
      <AppLockGate>
        <Text>Private content</Text>
      </AppLockGate>
    </ServicesProvider>,
  );
  expect(screen.queryByText("Private content")).toBeNull();
  await act(async () => resolve(null));
  expect(screen.getByText("Private content")).toBeTruthy();
});

it("fails closed when the preference read fails", async () => {
  jest
    .mocked(SecureStore.getItemAsync)
    .mockRejectedValue(new Error("store unavailable"));
  jest
    .mocked(LocalAuthentication.authenticateAsync)
    .mockResolvedValue({ success: false, error: "user_cancel" });
  const { services } = makeServices();
  await services.session.load();
  await render(
    <ServicesProvider services={services}>
      <AppLockGate>
        <Text>Private content</Text>
      </AppLockGate>
    </ServicesProvider>,
  );
  await waitFor(() => expect(LocalAuthentication.authenticateAsync).toHaveBeenCalled());
  expect(screen.queryByText("Private content")).toBeNull();
  expect(screen.getByTestId("app-lock")).toBeTruthy();
});
