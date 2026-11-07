import { Assessment } from "../data";
import { CARD_ROWS, Chart, ChartRow, charts } from "../charts";
import { count } from "../format";
import { go } from "../router";
import { Ref } from "./RichText";

function RowLabel({ row }: { row: ChartRow }) {
  return row.ref ? <Ref to={row.ref}>{row.label}</Ref> : <>{row.label}</>;
}

function Columns({ rows }: { rows: ChartRow[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="chart" role="img" aria-label="Column chart">
      {rows.map((r) => (
        <div className="col" key={r.label}>
          <div className="pair">
            <div className="bar" style={{ height: `${(r.value / max) * 100}%`, width: "50%", maxWidth: 64 }}>
              <b>{count(r.value)}</b>
            </div>
          </div>
          <span>
            <RowLabel row={r} />
          </span>
        </div>
      ))}
    </div>
  );
}

function Bars({ chart, rows }: { chart: Chart; rows: ChartRow[] }) {
  const max = Math.max(1, ...chart.rows.flatMap((r) => [r.value, r.previous ?? 0]));
  const pairs = chart.form === "pairs";
  return (
    <>
      {pairs && (
        <div className="legend">
          <span>
            <i className="soft" /> {chart.previousLabel}
          </span>
          <span>
            <i /> {chart.valueLabel}
          </span>
        </div>
      )}
      <div className="hbars">
        {rows.map((r) => (
          <div className="hbar" key={r.label}>
            <span className="strong">
              <RowLabel row={r} />
            </span>
            <div className="tracks">
              {pairs && (
                <div className="line">
                  {(r.previous ?? 0) > 0 && <div className="soft" style={{ width: `${((r.previous ?? 0) / max) * 80}%` }} />}
                  {count(r.previous ?? 0)}
                </div>
              )}
              <div className="line">
                {r.value > 0 && <div style={{ width: `${(r.value / max) * 80}%` }} />}
                {count(r.value)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function ChartCard({ chart }: { chart: Chart }) {
  const rows = chart.rows.slice(0, CARD_ROWS[chart.form]);
  const hidden = chart.rows.length - rows.length;
  return (
    <div className="chart-card">
      <h3>{chart.title}</h3>
      <div className="chart-body">
        {chart.rows.length === 0 ? (
          <p>No data</p>
        ) : chart.form === "columns" ? (
          <Columns rows={rows} />
        ) : (
          <Bars chart={chart} rows={rows} />
        )}
      </div>
      <div className="chart-foot">
        {hidden > 0 ? (
          <button onClick={() => go({ view: "stats", id: chart.id })}>Show all {chart.rows.length}</button>
        ) : (
          <button className="plain" onClick={() => go({ view: "stats", id: chart.id })}>
            Open as list
          </button>
        )}
      </div>
    </div>
  );
}

export function Trends({ data }: { data: Assessment }) {
  return (
    <div className="chart-grid">
      {charts(data).map((c) => (
        <ChartCard key={c.id} chart={c} />
      ))}
    </div>
  );
}
