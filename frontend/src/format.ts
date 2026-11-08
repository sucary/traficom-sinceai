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

export function longDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December"];
  return `${d} ${months[m - 1]} ${y}`;
}

export function daysUntil(iso: string, today = new Date()): number {
  const [y, m, d] = iso.split("-").map(Number);
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - start) / 86400000);
}

export function deadlineText(iso: string): string {
  const days = daysUntil(iso);
  if (days < 0) return "passed";
  if (days === 0) return "today";
  return `${days} ${days === 1 ? "day" : "days"} left`;
}

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
