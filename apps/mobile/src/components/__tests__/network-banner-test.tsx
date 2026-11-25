import { useNetInfo, type NetInfoState } from "@react-native-community/netinfo";
import { fireEvent, render, screen } from "@testing-library/react-native";
import { Text } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useKeyboardVerticalOffset } from "../keyboard-avoiding-form";
import {
  NetworkBanner,
  NetworkStatusBoundary,
  OFFLINE_MESSAGE,
} from "../network-banner";

const mockUseNetInfo = jest.mocked(useNetInfo);

function setConnectivity(
  isConnected: boolean | null,
  isInternetReachable: boolean | null,
): void {
  mockUseNetInfo.mockReturnValue({ isConnected, isInternetReachable } as NetInfoState);
}

function TopInset() {
  return <Text testID="top-inset">{useSafeAreaInsets().top}</Text>;
}

const INSETS = {
  initialMetrics: {
    frame: { x: 0, y: 0, width: 390, height: 844 },
    insets: { top: 47, left: 0, right: 0, bottom: 34 },
  },
};

describe("NetworkBanner", () => {
  it("is hidden when online", async () => {
    setConnectivity(true, true);
    await render(<NetworkBanner />);
    expect(screen.queryByText(OFFLINE_MESSAGE)).toBeNull();
  });

  it("is hidden while connectivity is still unknown", async () => {
    setConnectivity(null, null);
    await render(<NetworkBanner />);
    expect(screen.queryByText(OFFLINE_MESSAGE)).toBeNull();
  });

  it.each([
    ["disconnected", false, null],
    ["connected without internet", true, false],
  ])(
    "shows an accessible alert when %s",
    async (_label, isConnected, isInternetReachable) => {
      setConnectivity(isConnected, isInternetReachable);
      await render(<NetworkBanner />);
      const banner = screen.getByRole("alert");
      expect(banner).toHaveTextContent(OFFLINE_MESSAGE);
      expect(banner).toHaveProp("accessibilityLiveRegion", "polite");
    },
  );

  it("updates when connectivity changes", async () => {
    setConnectivity(true, true);
    await render(<NetworkBanner />);
    expect(screen.queryByRole("alert")).toBeNull();

    setConnectivity(false, false);
    await screen.rerender(<NetworkBanner />);
    expect(screen.getByRole("alert")).toBeOnTheScreen();

    setConnectivity(true, true);
    await screen.rerender(<NetworkBanner />);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("NetworkStatusBoundary", () => {
  it("passes the top inset through when online", async () => {
    const { SafeAreaProvider } = jest.requireActual<
      typeof import("react-native-safe-area-context")
    >("react-native-safe-area-context");
    setConnectivity(true, true);
    await render(
      <SafeAreaProvider {...INSETS}>
        <NetworkStatusBoundary>
          <TopInset />
        </NetworkStatusBoundary>
      </SafeAreaProvider>,
    );
    expect(await screen.findByTestId("top-inset")).toHaveTextContent("47");
  });

  it("gives the top inset to the banner when offline", async () => {
    const { SafeAreaProvider } = jest.requireActual<
      typeof import("react-native-safe-area-context")
    >("react-native-safe-area-context");
    setConnectivity(false, false);
    await render(
      <SafeAreaProvider {...INSETS}>
        <NetworkStatusBoundary>
          <TopInset />
        </NetworkStatusBoundary>
      </SafeAreaProvider>,
    );
    expect(await screen.findByTestId("top-inset")).toHaveTextContent("0");
    expect(screen.getByTestId("network-banner")).toHaveStyle({ paddingTop: 47 + 8 });
  });
});

function KeyboardOffset({ base }: { base: number }) {
  return <Text testID="keyboard-offset">{useKeyboardVerticalOffset(base)}</Text>;
}

describe("keyboard offset with the banner (m3)", () => {
  async function renderForm() {
    const { SafeAreaProvider } = jest.requireActual<
      typeof import("react-native-safe-area-context")
    >("react-native-safe-area-context");
    await render(
      <SafeAreaProvider {...INSETS}>
        <NetworkStatusBoundary>
          <KeyboardOffset base={50} />
        </NetworkStatusBoundary>
      </SafeAreaProvider>,
    );
  }

  it("adds the visible banner's height", async () => {
    setConnectivity(false, false);
    await renderForm();
    await fireEvent(await screen.findByTestId("network-banner"), "layout", {
      nativeEvent: { layout: { x: 0, y: 0, width: 390, height: 83 } },
    });
    expect(screen.getByTestId("keyboard-offset")).toHaveTextContent(String(50 + 83));
  });

  it("uses the given offset alone while online", async () => {
    setConnectivity(true, true);
    await renderForm();
    expect(await screen.findByTestId("keyboard-offset")).toHaveTextContent("50");
  });
});
