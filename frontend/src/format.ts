// Negative numbers use the true minus sign (U+2212) so the UI never shows a hyphen.
export function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "";
  const text = Math.abs(value).toFixed(digits);
  return value < 0 ? "−" + text : text;
}

export function count(value: number): string {
  return value.toLocaleString("en-GB");
}

export function withUnit(value: number | null, unit: string): string {
  return value === null ? "No value" : `${num(value)} ${unit}`;
}

// Margin convention: negative means above the limit.
export function margin(value: number | null, word = "limit"): string {
  if (value === null || value === undefined) return `No applicable ${word}`;
  if (value < 0) return `${num(-value)} dB over ${word}`;
  return `${num(value)} dB under ${word}`;
}

export function coord(lat: number, lon: number): string {
  return `${lat.toFixed(2)} N ${lon.toFixed(2)} E`;
}

export function limitWord(kind: string): string {
  return kind === "Terrestrial" ? "threshold" : "limit";
}
