import { useNetInfo, type NetInfoState } from "@react-native-community/netinfo";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { Keyboard, Text, type KeyboardEvent } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { keyboardOverlap, KeyboardAvoidingForm } from "../keyboard-avoiding-form";
import type { WindowFrame } from "../measure-in-window";
import { NetworkStatusBoundary } from "../network-banner";

// Jest has no native layout: the test decides where the form sits in the window.
let mockFrame: WindowFrame = { y: 0, height: 0 };
jest.mock("../measure-in-window", () => ({
  measureInWindow: (_ref: unknown, callback: (f: WindowFrame) => void) =>
    callback(mockFrame),
}));

type Listener = (event: KeyboardEvent) => void;
let listeners: Record<string, Listener>;

beforeEach(() => {
  listeners = {};
  jest.spyOn(Keyboard, "addListener").mockImplementation((type, listener) => {
    listeners[type] = listener as Listener;
    return { remove: jest.fn() } as unknown as ReturnType<typeof Keyboard.addListener>;
  });
  jest.spyOn(Keyboard, "isVisible").mockReturnValue(false);
});
afterEach(() => jest.restoreAllMocks());

function keyboardEvent(screenY: number): KeyboardEvent {
  return {
    duration: 250,
    easing: "keyboard",
    startCoordinates: { screenX: 0, screenY: 844, width: 390, height: 0 },
    endCoordinates: { screenX: 0, screenY, width: 390, height: 844 - screenY },
  } as KeyboardEvent;
}

function setOffline(offline: boolean) {
  jest.mocked(useNetInfo).mockReturnValue({
    isConnected: !offline,
    isInternetReachable: !offline,
  } as NetInfoState);
}

const form = () => screen.getByTestId("keyboard-avoiding-form");

const METRICS = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 47, left: 0, right: 0, bottom: 34 },
};

const tree = () => (
  <SafeAreaProvider initialMetrics={METRICS}>
    <NetworkStatusBoundary>
      <KeyboardAvoidingForm>
        <Text>form</Text>
      </KeyboardAvoidingForm>
    </NetworkStatusBoundary>
  </SafeAreaProvider>
);

async function renderForm() {
  await render(tree());
}

describe("keyboardOverlap", () => {
  it.each([
    [{ y: 100, height: 744 }, null, 0],
    [{ y: 100, height: 744 }, 500, 344],
    [{ y: 100, height: 300 }, 500, 0],
    [{ y: 0, height: 844 }, 844, 0],
  ])("frame %o, keyboard top %p -> %p", (f, top, expected) => {
    expect(keyboardOverlap(f, top)).toBe(expected);
  });
});

describe("KeyboardAvoidingForm", () => {
  it("pads by the keyboard's overlap and resets when it hides", async () => {
    setOffline(false);
    mockFrame = { y: 100, height: 744 }; // under a header, down to the screen bottom
    await renderForm();
    expect(form()).toHaveStyle({ paddingBottom: 0 });

    await act(() => listeners.keyboardWillChangeFrame!(keyboardEvent(500)));
    expect(form()).toHaveStyle({ paddingBottom: 344 });

    await act(() => listeners.keyboardWillHide!(keyboardEvent(844)));
    expect(form()).toHaveStyle({ paddingBottom: 0 });
  });

  it("recomputes when the offline banner appears with the keyboard open (R2-5)", async () => {
    setOffline(false);
    mockFrame = { y: 100, height: 700 }; // bottom edge at 800 (e.g. above a toolbar)
    await renderForm();
    await act(() => listeners.keyboardWillChangeFrame!(keyboardEvent(500)));
    expect(form()).toHaveStyle({ paddingBottom: 300 });

    // Going offline: the banner pushes the form down. Native layout reports the
    // new frame through onLayout; no keyboard event fires.
    setOffline(true);
    await screen.rerender(tree());
    expect(screen.getByTestId("network-banner")).toBeOnTheScreen();
    mockFrame = { y: 160, height: 700 }; // bottom edge now at 860
    await fireEvent(form(), "layout", {
      nativeEvent: { layout: { x: 0, y: 60, width: 390, height: 700 } },
    });
    expect(form()).toHaveStyle({ paddingBottom: 360 });
  });

  it("picks up a keyboard that is already open when it mounts", async () => {
    setOffline(false);
    jest.mocked(Keyboard.isVisible).mockReturnValue(true);
    jest
      .spyOn(Keyboard, "metrics")
      .mockReturnValue({ screenX: 0, screenY: 600, width: 390, height: 244 });
    mockFrame = { y: 100, height: 744 };
    await renderForm();
    expect(form()).toHaveStyle({ paddingBottom: 244 });
  });
});
