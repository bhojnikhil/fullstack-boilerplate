import QRCode from "qrcode";
import { useMemo } from "react";
import { View } from "react-native";

/** Renders `value` as a QR code with plain Views (no native module). */
export function QrCode({ value, size = 220 }: { value: string; size?: number }) {
  const modules = useMemo(() => {
    const { modules: grid } = QRCode.create(value, { errorCorrectionLevel: "M" });
    return { count: grid.size, data: grid.data };
  }, [value]);
  const cell = size / modules.count;
  const rows = Array.from({ length: modules.count }, (_, row) => row);
  return (
    <View
      accessible
      accessibilityLabel="QR code for the invitation link"
      // Always dark-on-light, whatever the theme, so scanners can read it.
      style={{ width: size, height: size, backgroundColor: "#ffffff", padding: 0 }}
    >
      {rows.map((row) => (
        <View key={row} style={{ flexDirection: "row", height: cell }}>
          {rows.map((column) => (
            <View
              key={column}
              style={{
                width: cell,
                height: cell,
                backgroundColor: modules.data[row * modules.count + column]
                  ? "#000000"
                  : "#ffffff",
              }}
            />
          ))}
        </View>
      ))}
    </View>
  );
}
