import { useState } from "react";
import { Assessment } from "../data";
import { charts } from "../charts";
import { count } from "../format";
import { Ref } from "../components/RichText";

type Sort = "value" | "label" | "change";

export function StatsPage({ data, id }: { data: Assessment; id: string }) {
  const chart = charts(data).find((c) => c.id === id);
  const [sort, setSort] = useState<Sort>("value");

  if (!chart) {
    return (
      <div className="page">
        <section>
          <h2>Statistics not found</h2>
          <a href="#/">Back to the overview</a>
        </section>
      </div>
    );
  }

  const pairs = chart.form === "pairs";
  const change = (r: { value: number; previous?: number }) => r.value - (r.previous ?? 0);
  const rows = [...chart.rows].sort((a, b) =>
    sort === "label" ? a.label.localeCompare(b.label) : sort === "change" ? change(b) - change(a) : b.value - a.value,
  );
  const max = Math.max(1, ...chart.rows.flatMap((r) => [r.value, r.previous ?? 0]));
  const total = chart.rows.reduce((s, r) => s + r.value, 0);

  return (
    <div className="page">
      <div className="detail-head">
        <button className="plain" onClick={() => history.back()}>
          Back
        </button>
        <h1>{chart.title}</h1>
        <div className="controls">
          <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="value">Sort by {chart.valueLabel}</option>
            <option value="label">Sort by name</option>
            {pairs && <option value="change">Sort by change</option>}
          </select>
        </div>
      </div>

      <section>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                {pairs && <th className="num">{chart.previousLabel}</th>}
                <th className="num">{chart.valueLabel}</th>
                {pairs && <th className="num">Change</th>}
                {!pairs && <th className="num">Share</th>}
                <th className="bar-col">Distribution</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td className="strong nowrap">{r.ref ? <Ref to={r.ref}>{r.label}</Ref> : r.label}</td>
                  {pairs && <td className="num">{count(r.previous ?? 0)}</td>}
                  <td className="num">{count(r.value)}</td>
                  {pairs && (
                    <td className="num">
                      {change(r) > 0 ? "+" : change(r) < 0 ? "−" : ""}
                      {count(Math.abs(change(r)))}
                    </td>
                  )}
                  {!pairs && <td className="num">{total ? Math.round((r.value / total) * 100) : 0}%</td>}
                  <td className="bar-col">
                    <div className="mini">
                      {pairs && <div className="soft" style={{ width: `${((r.previous ?? 0) / max) * 100}%` }} />}
                      <div style={{ width: `${(r.value / max) * 100}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
