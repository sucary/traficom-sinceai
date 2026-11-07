import { Assessment, Change, Notice } from "../data";
import { count } from "../format";

function Pairs({ rows, previous, current, wide }: { rows: Change[]; previous: string; current: string; wide?: boolean }) {
  const max = Math.max(1, ...rows.flatMap((a) => [a.previous, a.current]));
  return (
    <>
      <div className="legend">
        <span>
          <i className="soft" /> {previous}
        </span>
        <span>
          <i /> {current}
        </span>
      </div>
      <div className="hbars">
        {rows.map((a) => (
          <div className={"hbar" + (wide ? " wide" : "")} key={a.label}>
            <span className="strong">{a.label}</span>
            <div className="tracks">
              <div className="line">
                {a.previous > 0 && <div className="soft" style={{ width: `${(a.previous / max) * 80}%` }} />}
                {count(a.previous)}
              </div>
              <div className="line">
                {a.current > 0 && <div style={{ width: `${(a.current / max) * 80}%` }} />}
                {count(a.current)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function IssueColumns({ data }: { data: Assessment }) {
  const max = Math.max(1, ...data.issues.map((i) => i.noticesOfConcern));
  return (
    <div className="chart" role="img" aria-label="Notices of concern by issue">
      {data.issues.map((i) => (
        <div className="col" key={i.id}>
          <div className="pair">
            <div className="bar" style={{ height: `${(i.noticesOfConcern / max) * 100}%`, width: "50%", maxWidth: 64 }}>
              <b>{i.noticesOfConcern}</b>
            </div>
          </div>
          <span>{i.label}</span>
        </div>
      ))}
    </div>
  );
}

function ByAdministration({ notices }: { notices: Notice[] }) {
  const counts = new Map<string, number>();
  notices.forEach((n) => counts.set(n.administration, (counts.get(n.administration) ?? 0) + 1));
  const rows = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  const max = Math.max(1, ...rows.map((r) => r[1]));
  return (
    <div className="hbars">
      {rows.map(([adm, n]) => (
        <div className="hbar" key={adm}>
          <span className="strong">{adm}</span>
          <div className="line">
            <div style={{ width: `${(n / max) * 80}%` }} />
            {n}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Trends({ data }: { data: Assessment }) {
  return (
    <>
      <div className="grid2">
        <div>
          <h3>Notices of concern by issue</h3>
          <IssueColumns data={data} />
        </div>
        <div>
          <h3>Notices of concern by administration</h3>
          <ByAdministration notices={data.notices} />
        </div>
      </div>
      {data.trends.map((t) => (
        <section className="grid2" key={t.current}>
          <div>
            <h3>Terrestrial activity by administration</h3>
            <Pairs rows={t.administrations} previous={t.previous} current={t.current} />
          </div>
          <div>
            <h3>Terrestrial activity by band</h3>
            <Pairs rows={t.bands} previous={t.previous} current={t.current} wide />
          </div>
        </section>
      ))}
    </>
  );
}
