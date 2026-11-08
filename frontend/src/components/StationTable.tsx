import { Notice, label } from "../data";
import { coord, limitWord, margin, num } from "../format";
import { stationRef } from "../links";
import { go } from "../router";
import { Ref } from "./RichText";

export function StationTable({ notice, limit }: { notice: Notice; limit?: number }) {
  const space = notice.kind === "Space";
  const word = limitWord(notice.kind);
  const rows = limit === undefined ? notice.stations : notice.stations.slice(0, limit);
  const hidden = notice.stations.length - rows.length;
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{space ? "Station" : "Point"}</th>
              <th>Location</th>
              <th>{space ? "Protected band" : "Frequency"}</th>
              <th>Status</th>
              {!space && <th className="num">Distance</th>}
              <th className="num">{space ? "PFD" : "Field strength"}</th>
              <th className="num">{space ? "Limit" : "Threshold"}</th>
              <th className="num">Margin</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <tr key={s.id + i}>
                <td className="strong">{/^\d+$/.test(s.id) ? <Ref to={stationRef(s.id)}>{s.id}</Ref> : s.id}</td>
                <td className="nowrap">{coord(s.latitude, s.longitude)}</td>
                <td className="nowrap">{s.band}</td>
                <td className="nowrap">{label(s.status)}</td>
                {!space && <td className="num">{num(s.distanceKm)} km</td>}
                <td className="num">{num(s.value)}</td>
                <td className="num">{num(s.limit)}</td>
                <td className="num">{margin(s.marginDb, word)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <div className="more">
          <button onClick={() => go({ view: "cases", key: notice.key })}>
            Show all {notice.stations.length} {space ? "cases" : "points"}
          </button>
        </div>
      )}
    </>
  );
}
