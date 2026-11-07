import { ReactNode } from "react";
import { Notice, label } from "../data";
import { coord, limitWord, margin, num, withUnit } from "../format";
import { go, href } from "../router";
import { queueQuestion } from "../chatStore";
import { adminRef, noticeRef, stationRef } from "../links";
import { InlineText, Ref } from "./RichText";
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
    ["Provision", notice.provision],
    ["Protected band", notice.band],
    ["Reference bandwidth", notice.referenceBandwidth],
  ];
  if (notice.publicationDate) facts.push(["Published", notice.publicationDate]);
  if (notice.elevationDeg !== null) facts.push(["Worst elevation", num(notice.elevationDeg) + "°"]);
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
          <h2>{space ? "PFD vs limit" : "Field strength vs threshold"}</h2>
          <Bars notice={notice} />
        </div>
        <div>
          <h2>Governing rule</h2>
          <div className="rule">
            <p className="strong">{notice.rule.id || "No governing rule"}</p>
            {notice.rule.text && <p>{notice.rule.text}</p>}
            <p>{[c.document, c.provision, ...pages].filter(Boolean).join(", ")}</p>
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
        <h2>{space ? "Affected Finnish stations" : "Assessment points"}</h2>
        <StationTable notice={notice} limit={STATION_PAGE} />
      </section>

      <section className="grid2">
        <div>
          <h2>Assumptions</h2>
          <ul className="list">
            {notice.assumptions.map((a) => (
              <li key={a}>
                <InlineText text={a} />
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2>Caveats</h2>
          <ul className="list">
            {notice.caveats.map((c) => (
              <li key={c}>
                <InlineText text={c} />
              </li>
            ))}
          </ul>
          {notice.otherCaseCaveats && notice.otherCaseCaveats.length > 0 && (
            <>
              <h3>Other cases of this notice</h3>
              <p>These apply to other cases of this notice, not to the worst case values above.</p>
              <ul className="list">
                {notice.otherCaseCaveats.map((c) => (
                  <li key={c.text}>
                    <InlineText text={`${c.text} (${c.cases} ${c.cases === 1 ? "case" : "cases"})`} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </section>

      <section>
        <h2>Source rows</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Table</th>
                <th>Rows</th>
                <th>SHA256</th>
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

      <section>
        <a href={href({ view: "home" })}>Back to all notices</a>
      </section>
    </div>
  );
}
