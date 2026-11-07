import { useState } from "react";
import { Notice, label } from "../data";
import { limitWord, margin } from "../format";
import { go } from "../router";
import { adminRef } from "../links";
import { Ref } from "./RichText";

const PAGE = 15;

export function NoticeList({ notices }: { notices: Notice[] }) {
  const [shown, setShown] = useState(PAGE);
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
      {shown < notices.length && (
        <div className="more">
          <button onClick={() => setShown(notices.length)}>Show all {notices.length} notices</button>
        </div>
      )}
    </>
  );
}
