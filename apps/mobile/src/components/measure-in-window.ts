import type { RefObject } from "react";
import type { HostInstance } from "react-native";

export interface WindowFrame {
  y: number;
  height: number;
}

/**
 * Measures a view in window coordinates. A separate module so tests can
 * supply frames (Jest has no native layout).
 */
export function measureInWindow(
  ref: RefObject<HostInstance | null>,
  callback: (frame: WindowFrame) => void,
): void {
  ref.current?.measureInWindow((_x, y, _width, height) => callback({ y, height }));
}
