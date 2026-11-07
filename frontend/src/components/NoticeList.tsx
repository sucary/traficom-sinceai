import { Notice, label } from "../data";
import { limitWord, margin } from "../format";
import { Route, go } from "../router";
import { adminRef } from "../links";
import { Ref } from "./RichText";

/** Ranked notices. With `limit`, only the first rows show and "Show all" opens
 *  `full`, the same list in its own view. */
export function NoticeList({ notices, limit, full }: { notices: Notice[]; limit?: number; full?: Route }) {
  const shown = limit ?? notices.length;
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="num">Priority</th>
              <th>Administration</th>
              <th>Satellite or station</th>
              <th>Notice</th>
              <th>Status</th>
              <th className="num">Worst margin</th>
              <th className="num">Finnish stations affected</th>
            </tr>
          </thead>
          <tbody>
            {notices.slice(0, shown).map((n, i) => (
              <tr
                key={n.key}
                className="click"
                tabIndex={0}
                onClick={() => go({ view: "notice", key: n.key })}
                onKeyDown={(e) => e.key === "Enter" && go({ view: "notice", key: n.key })}
              >
                <td className="num">{i + 1}</td>
                <td>
                  <Ref to={adminRef(n.administration)}>{n.administrationName}</Ref>
                </td>
                <td className="strong">{n.name}</td>
                <td>{n.noticeId}</td>
                <td className="nowrap">{label(n.status)}</td>
                <td className="num">{margin(n.worstMarginDb, limitWord(n.kind))}</td>
                <td className="num">{n.stationsAffected}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown < notices.length && full && (
        <div className="more">
          <button onClick={() => full && go(full)}>Show all {notices.length} notices</button>
        </div>
      )}
    </>
  );
}
