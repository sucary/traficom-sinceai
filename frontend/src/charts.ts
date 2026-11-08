import type { Assessment } from "./data";

export interface ChartRow {
  label: string;
  value: number;
  previous?: number;
  ref?: string;
  date?: string;
}

export interface Chart {
  id: string;
  title: string;
  form: "columns" | "bars" | "pairs";
  rows: ChartRow[];
  valueLabel: string;
  previousLabel?: string;
  sortable?: boolean;
}

export type ChartSort = "date" | "number";

export function sortedRows(chart: Chart, sort: ChartSort, limit?: number): ChartRow[] {
  if (sort === "number") {
    const rows = [...chart.rows].sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
    return limit === undefined ? rows : rows.slice(0, limit);
  }
  const rows = [...chart.rows].sort(
    (a, b) => (a.date ?? "").localeCompare(b.date ?? "") || a.label.localeCompare(b.label),
  );
  return limit === undefined ? rows : rows.slice(Math.max(0, rows.length - limit));
}

export const CARD_ROWS: Record<Chart["form"], number> = { columns: 6, bars: 8, pairs: 4 };

export function charts(data: Assessment): Chart[] {
  const byAdmin = new Map<string, number>();
  data.notices.forEach((n) => byAdmin.set(n.administration, (byAdmin.get(n.administration) ?? 0) + 1));

  const list: Chart[] = [
    {
      id: "notices-by-issue",
      title: "Notices of concern by issue",
      form: "columns",
      valueLabel: "Notices of concern",
      sortable: true,
      rows: data.issues.map((i) => ({
        label: i.label,
        value: i.noticesOfConcern,
        ref: `issue:${i.id}`,
        date: i.published,
      })),
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
