// Every statistics chart, described once so the overview cards and the
// full list view (#/stats/<id>) show the same rows.
import type { Assessment } from "./data";

export interface ChartRow {
  label: string;
  value: number; // single series, or the current issue for comparisons
  previous?: number; // set for comparisons between two issues
  ref?: string; // where the row label leads
}

export interface Chart {
  id: string;
  title: string;
  form: "columns" | "bars" | "pairs";
  rows: ChartRow[];
  valueLabel: string;
  previousLabel?: string;
}

/** Rows that fit inside a card of fixed size; the rest is behind "Show all". */
export const CARD_ROWS: Record<Chart["form"], number> = { columns: 6, bars: 8, pairs: 5 };

export function charts(data: Assessment): Chart[] {
  const byAdmin = new Map<string, number>();
  data.notices.forEach((n) => byAdmin.set(n.administration, (byAdmin.get(n.administration) ?? 0) + 1));

  const list: Chart[] = [
    {
      id: "notices-by-issue",
      title: "Notices of concern by issue",
      form: "columns",
      valueLabel: "Notices of concern",
      rows: data.issues.map((i) => ({ label: i.label, value: i.noticesOfConcern, ref: `issue:${i.id}` })),
    },
    {
      id: "notices-by-administration",
      title: "Notices of concern by administration",
      form: "bars",
      valueLabel: "Notices of concern",
      rows: [...byAdmin.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([code, value]) => ({ label: code, value, ref: `administration:${code}` })),
    },
  ];

  data.trends.forEach((t, i) => {
    const suffix = data.trends.length > 1 ? ` ${t.current}` : "";
    list.push(
      {
        id: `terrestrial-administrations-${i}`,
        title: `Terrestrial activity by administration${suffix}`,
        form: "pairs",
        valueLabel: t.current,
        previousLabel: t.previous,
        rows: t.administrations.map((a) => ({
          label: a.label,
          value: a.current,
          previous: a.previous,
          ref: data.notices.some((n) => n.administration === a.label) ? `administration:${a.label}` : undefined,
        })),
      },
      {
        id: `terrestrial-bands-${i}`,
        title: `Terrestrial activity by band${suffix}`,
        form: "pairs",
        valueLabel: t.current,
        previousLabel: t.previous,
        rows: t.bands.map((b) => ({ label: b.label, value: b.current, previous: b.previous })),
      },
    );
  });
  return list;
}
