import { renderHook } from "@testing-library/react-native";
import { colors, getTheme, type ColorTokens } from "../tokens";
import { useColorScheme } from "../use-color-scheme";
import { toNavigationTheme, useTheme } from "../use-theme";

jest.mock("../use-color-scheme", () => ({ useColorScheme: jest.fn() }));

// WCAG 2.x relative luminance / contrast ratio.
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

// Foreground/background pairs the components actually render together.
const PAIRS: [keyof ColorTokens, keyof ColorTokens][] = [
  ["text", "background"],
  ["text", "surface"],
  ["textMuted", "background"],
  ["textMuted", "surface"],
  ["onPrimary", "primary"],
  ["primary", "background"],
  ["danger", "background"],
  ["danger", "surface"],
  ["onDanger", "danger"],
  ["onWarning", "warningBackground"],
];

describe("design tokens", () => {
  it("defines the same tokens for light and dark", () => {
    expect(Object.keys(colors.dark).sort()).toEqual(Object.keys(colors.light).sort());
  });

  it.each(["light", "dark"] as const)("uses 6-digit hex colors in %s", (scheme) => {
    for (const value of Object.values(colors[scheme])) {
      expect(value).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  describe.each(["light", "dark"] as const)("%s scheme", (scheme) => {
    it.each(PAIRS)("%s on %s meets WCAG AA (4.5:1)", (fg, bg) => {
      expect(contrast(colors[scheme][fg], colors[scheme][bg])).toBeGreaterThanOrEqual(
        4.5,
      );
    });
  });

  it("maps the OS scheme to a theme, defaulting to light", () => {
    expect(getTheme("dark").colors).toBe(colors.dark);
    expect(getTheme("light").colors).toBe(colors.light);
    expect(getTheme(null).scheme).toBe("light");
    expect(getTheme("unspecified").scheme).toBe("light");
  });
});

describe("useTheme", () => {
  it.each(["light", "dark"] as const)("follows the OS %s setting", async (scheme) => {
    jest.mocked(useColorScheme).mockReturnValue(scheme);
    const { result } = await renderHook(() => useTheme());
    expect(result.current.scheme).toBe(scheme);
    expect(result.current.colors).toBe(colors[scheme]);
  });

  it("updates when the OS setting changes", async () => {
    jest.mocked(useColorScheme).mockReturnValue("light");
    const { result, rerender } = await renderHook(() => useTheme());
    expect(result.current.scheme).toBe("light");
    jest.mocked(useColorScheme).mockReturnValue("dark");
    await rerender({});
    expect(result.current.scheme).toBe("dark");
  });

  it("maps tokens onto the navigation theme", () => {
    const nav = toNavigationTheme(getTheme("dark"));
    expect(nav.dark).toBe(true);
    expect(nav.colors.background).toBe(colors.dark.background);
    expect(nav.colors.text).toBe(colors.dark.text);
    expect(toNavigationTheme(getTheme("light")).dark).toBe(false);
  });
});
