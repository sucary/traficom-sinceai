import { useState } from "react";
import { NeighbourRow, Trend } from "../data";
import { margin, num } from "../format";
import { refToRoute } from "../links";
import { go } from "../router";
import { Ref } from "./RichText";

const LIMIT = 10;

const worstFirst = (a: number | null, b: number | null) =>
  a === null ? (b === null ? 0 : 1) : b === null ? -1 : a - b;

const priority = (a: NeighbourRow, b: NeighbourRow) =>
  b.flags.length - a.flags.length || worstFirst(a.marginDb, b.marginDb);

export function NeighbourActivity({ trend }: { trend: Trend }) {
  const [all, setAll] = useState(false);
  const rows = [...(trend.neighbourActivity?.rows ?? [])].sort(priority);
  const shown = all ? rows : rows.slice(0, LIMIT);
  const open = (r: NeighbourRow) => {
    const route = r.assignment.ref ? refToRoute(r.assignment.ref) : null;
    if (route) go(route);
  };
  return (
    <section>
      <h2>Neighbour activity in {trend.current}</h2>
      {rows.length === 0 ? (
        <p>No neighbouring administration has base stations within range of Finland in this issue.</p>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Priority</th>
                  <th>Administration</th>
                  <th>Assignment</th>
                  <th className="num">Distance to border</th>
                  <th className="num">Margin</th>
                  <th>Why flagged</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r, i) => (
                  <tr
                    key={r.assignment.text + i}
                    className={r.assignment.ref ? "click" : undefined}
                    tabIndex={r.assignment.ref ? 0 : undefined}
                    onClick={() => open(r)}
                    onKeyDown={(e) => e.key === "Enter" && open(r)}
                  >
                    <td className="num">{i + 1}</td>
                    <td>
                      {r.administration.ref ? (
                        <Ref to={r.administration.ref}>{r.administration.text}</Ref>
                      ) : (
                        r.administration.text
                      )}
                    </td>
                    <td className="strong">{r.assignment.text}</td>
                    <td className="num">{r.distanceKm === null ? "" : `${num(r.distanceKm)} km`}</td>
                    <td className="num">{margin(r.marginDb, "threshold")}</td>
                    <td>{r.flags.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > LIMIT && !all && (
            <div className="more">
              <button onClick={() => setAll(true)}>Show all {rows.length} base stations</button>
            </div>
          )}
        </>
      )}
      {(trend.neighbourActivity?.notes ?? []).map((n) => (
        <p key={n}>{n}</p>
      ))}
    </section>
  );
}
