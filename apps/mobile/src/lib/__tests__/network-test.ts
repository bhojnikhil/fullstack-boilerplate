import NetInfo, { type NetInfoState } from "@react-native-community/netinfo";
import { focusManager, onlineManager } from "@tanstack/react-query";
import { AppState, type AppStateStatus } from "react-native";

import { connectQueryManagers, isOffline } from "../network";

const mockNetInfo = jest.mocked(NetInfo);

describe("isOffline", () => {
  it.each([
    [true, true, false],
    [null, null, false],
    [true, null, false],
    [false, null, true],
    [true, false, true],
  ])(
    "isConnected=%p isInternetReachable=%p -> %p",
    (isConnected, isInternetReachable, offline) => {
      expect(isOffline({ isConnected, isInternetReachable } as NetInfoState)).toBe(
        offline,
      );
    },
  );
});

describe("connectQueryManagers (m4)", () => {
  let appStateHandler: ((status: AppStateStatus) => void) | undefined;
  const remove = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockNetInfo.refresh.mockResolvedValue({} as NetInfoState);
    jest.spyOn(AppState, "addEventListener").mockImplementation((_type, handler) => {
      appStateHandler = handler as (status: AppStateStatus) => void;
      return { remove };
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
    onlineManager.setOnline(true);
  });

  it("re-checks connectivity and refocuses queries when the app comes to the foreground", () => {
    const cleanup = connectQueryManagers();
    const setFocused = jest.spyOn(focusManager, "setFocused");

    appStateHandler!("background");
    expect(setFocused).toHaveBeenLastCalledWith(false);
    expect(mockNetInfo.refresh).not.toHaveBeenCalled();

    appStateHandler!("active");
    expect(setFocused).toHaveBeenLastCalledWith(true);
    expect(mockNetInfo.refresh).toHaveBeenCalledTimes(1);

    cleanup();
    expect(remove).toHaveBeenCalled();
  });

  it("drives TanStack's online state from NetInfo", () => {
    connectQueryManagers();
    expect(mockNetInfo.addEventListener).toHaveBeenCalledTimes(1);
    const listener = mockNetInfo.addEventListener.mock.calls[0]![0];

    listener({ isConnected: false, isInternetReachable: false } as NetInfoState);
    expect(onlineManager.isOnline()).toBe(false);
    listener({ isConnected: true, isInternetReachable: true } as NetInfoState);
    expect(onlineManager.isOnline()).toBe(true);
  });

  it("unsubscribes from NetInfo on cleanup", () => {
    const unsubscribe = jest.fn();
    mockNetInfo.addEventListener.mockReturnValueOnce(unsubscribe);
    connectQueryManagers()();
    expect(unsubscribe).toHaveBeenCalled();
  });
});
