import { ReactNode } from "react";
import { Notice, label } from "../data";
import { coord, deadlineText, limitWord, longDate, margin, num, withUnit } from "../format";
import { go } from "../router";
import { queueQuestion } from "../chatStore";
import { adminRef, noticeRef, stationRef } from "../links";
import { Ref } from "./RichText";
import { StationTable } from "./StationTable";
import { BackIcon } from "./Icons";

const STATION_PAGE = 20;

function Bars({ notice }: { notice: Notice }) {
  if (notice.value === null || notice.limit === null) return <p>No applicable limit for this notice.</p>;
  const floor = Math.min(notice.value, notice.limit) - 15;
  const ceil = Math.max(notice.value, notice.limit) + 5;
  const w = (v: number) => `${((v - floor) / (ceil - floor)) * 100}%`;
  return (
    <div className="bars">
      <div className="bar-row">
        <span className="strong">{notice.kind === "Space" ? "PFD" : "Field"}</span>
        <div className="bar-track">
          <div className="bar-fill" style={{ width: w(notice.value) }} />
        </div>
        <span>{withUnit(notice.value, notice.unit)}</span>
      </div>
      <div className="bar-row">
        <span className="strong">{notice.kind === "Space" ? "Limit" : "Threshold"}</span>
        <div className="bar-track">
          <div className="bar-fill soft" style={{ width: w(notice.limit) }} />
        </div>
        <span>{withUnit(notice.limit, notice.unit)}</span>
      </div>
    </div>
  );
}

export function NoticeDetail({ notice }: { notice: Notice }) {
  const word = limitWord(notice.kind);
  const space = notice.kind === "Space";
  const facts: [string, ReactNode][] = [
    ["Status", label(notice.status)],
    ["Worst margin", margin(notice.worstMarginDb, word)],
    ["Finnish stations affected", String(notice.stationsAffected)],
    [
      "Administration",
      <Ref to={adminRef(notice.administration)}>
        {notice.administrationName} ({notice.administration})
      </Ref>,
    ],
    [space ? "Notice" : "Assignment", notice.noticeId],
    ["ITU procedure", notice.provision],
    [space ? "Finnish protected band" : "Frequency", notice.band],
    ["Reference bandwidth", notice.referenceBandwidth],
  ];
  if (notice.publicationDate) facts.push(["Published", notice.publicationDate]);
  if (space)
    facts.push([
      "Response deadline",
      notice.responseDeadline?.date
        ? `${longDate(notice.responseDeadline.date)}, ${deadlineText(notice.responseDeadline.date)}, ${notice.responseDeadline.rule}`
        : "None, notification",
    ]);
  if (notice.elevationDeg !== null) facts.push(["Elevation at worst case", num(notice.elevationDeg) + "°"]);
  if (notice.distanceKm !== undefined) facts.push(["Distance to Finland", num(notice.distanceKm) + " km"]);
  if (space) facts.push(["Cases of concern", String(notice.casesOfConcern)]);

  const c = notice.citation;
  const pages = [c.printedPage && `printed page ${c.printedPage}`, c.pdfPage && `PDF page ${c.pdfPage}`].filter(Boolean);

  return (
    <div className="page">
      <div className="detail-head">
        <button className="plain back-btn" onClick={() => history.back()}>
          <BackIcon />
          Back
        </button>
        <h1>{notice.name}</h1>
      </div>

      <section>
        <dl className="facts">
          {facts.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <div className="actions detail-actions">
          <button onClick={() => go({ view: "letter", scope: "notice", key: notice.key })}>
            Draft letter for this notice
          </button>
          <button
            className="plain"
            onClick={() => go({ view: "letter", scope: "administration", key: notice.administration })}
          >
            Draft letter for {notice.administrationName}
          </button>
          <button
            className="plain"
            onClick={() => {
              queueQuestion(`Explain ${notice.name} notice ${notice.noticeId}`, noticeRef(notice.key));
              go({ view: "chat" });
            }}
          >
            Ask about this notice
          </button>
        </div>
      </section>

      <section className="grid2">
        <div>
          <h2>{space ? "Calculated PFD and limit" : "Calculated field strength and threshold"}</h2>
          <Bars notice={notice} />
        </div>
        <div>
          <h2>{space ? "Applicable limit" : "Applicable threshold"}</h2>
          <div className="rule">
            <p className="strong">{notice.rule.id || "No governing rule"}</p>
            {notice.rule.text && <p>{notice.rule.text}</p>}
            <p>{[c.document, c.provision, ...pages].filter(Boolean).join(", ")}</p>
            {notice.nationalContext && (
              <p>
                Finnish use in M4: mobile service {label(notice.nationalContext.mobileInFinland).toLowerCase()}
                {notice.nationalContext.m4Bands.length > 0 && ` in ${notice.nationalContext.m4Bands.join(", ")}`}
              </p>
            )}
            {c.url && (
              <p>
                <a href={c.url} target="_blank" rel="noreferrer">
                  Open source document
                </a>
              </p>
            )}
          </div>
        </div>
      </section>

      <section>
        <h2>{space ? "Affected Finnish stations" : "Calculation points"}</h2>
        <StationTable notice={notice} limit={STATION_PAGE} />
      </section>

      <section>
        <h2>Source data</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Table</th>
                <th>Row numbers</th>
                <th>SHA-256 checksum</th>
              </tr>
            </thead>
            <tbody>
              {notice.sourceRows.map((r) => (
                <tr key={r.table + r.rows}>
                  <td>{r.dataset}</td>
                  <td>{r.table}</td>
                  <td>{r.rows}</td>
                  <td>{r.sha256}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

    </div>
  );
}
