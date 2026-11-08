import { useMemo, useState } from "react";
import { Notice, label } from "../data";
import { limitWord, longDate, margin } from "../format";
import { Route, go } from "../router";
import { adminRef } from "../links";
import { Ref } from "./RichText";
import { Dropdown } from "./Dropdown";

type NoticeSort = "margin" | "stations" | "deadline";

function compareNotices(sort: NoticeSort, a: Notice, b: Notice): number {
  if (sort === "stations") {
    return b.stationsAffected - a.stationsAffected || (a.worstMarginDb ?? Infinity) - (b.worstMarginDb ?? Infinity);
  }
  if (sort === "deadline") {
    const aDate = a.responseDeadline?.date || "9999-12-31";
    const bDate = b.responseDeadline?.date || "9999-12-31";
    return aDate.localeCompare(bDate) || (a.worstMarginDb ?? Infinity) - (b.worstMarginDb ?? Infinity);
  }
  return (a.worstMarginDb ?? Infinity) - (b.worstMarginDb ?? Infinity);
}

export function NoticeList({ notices, limit, full }: { notices: Notice[]; limit?: number; full?: Route }) {
  const [sort, setSort] = useState<NoticeSort>("margin");
  const sorted = useMemo(() => notices.slice().sort((a, b) => compareNotices(sort, a, b)), [notices, sort]);
  const shown = limit ?? notices.length;
  const space = notices.some((n) => n.kind === "Space");
  return (
    <>
      <div className="notice-sort sort-by">
        <span>Sort by</span>
        <Dropdown
          compact
          ariaLabel="Sort notices by"
          value={sort}
          onChange={(value) => setSort(value as NoticeSort)}
          options={[
            { value: "margin", label: "Margin" },
            { value: "stations", label: "Stations affected" },
            { value: "deadline", label: "Deadline" },
          ]}
        />
      </div>
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
              {space && <th>Response deadline</th>}
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, shown).map((n, i) => (
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
                {space && (
                  <td className="nowrap">{n.responseDeadline?.date ? longDate(n.responseDeadline.date) : "None"}</td>
                )}
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
