import { useState } from "react";
import { Assessment } from "../data";
import { count, limitWord, margin } from "../format";
import { queueQuestion } from "../chatStore";
import { Ref } from "../components/RichText";
import { noticeRef, stationRef } from "../links";
import { go } from "../router";
import { BackIcon } from "../components/Icons";

const STATIONS_SHOWN = 50;

const useWord: Record<string, string> = {
  primary: "Primary",
  secondary: "Secondary",
  not_listed: "Not listed",
};

// The same results seen from the Finnish side: which frequency bands and which stations
// are exposed, regardless of which notice causes it.
export function UsagePage({ data }: { data: Assessment }) {
  const [allStations, setAllStations] = useState(false);
  const usage = data.usage;

  if (!usage || (usage.bands.length === 0 && usage.stations.length === 0)) {
    return (
      <div className="page">
        <section>
          <h2>No Finnish usage view</h2>
          <p>Run python backend/scripts/export_frontend_data.py in the project folder, then reload this page.</p>
        </section>
      </div>
    );
  }

  const stations = allStations ? usage.stations : usage.stations.slice(0, STATIONS_SHOWN);

  return (
    <div className="page">
      <div className="detail-head">
        <button className="plain back-btn" onClick={() => history.back()}>
          <BackIcon />
          Back
        </button>
        <h1>Impact on Finnish use</h1>
        <div className="actions">
          <button
            onClick={() => {
              queueQuestion("Which Finnish frequency bands and stations are most affected?");
              go({ view: "chat" });
            }}
          >
            Ask about Finnish impact
          </button>
        </div>
      </div>

      <section>
        <p>
          The same screening results grouped by Finnish frequency band and by Finnish station. A case is one notice
          against one Finnish station and protected band. Space bands are Finland&apos;s M4 allocation bands;
          national use is Finland&apos;s fixed or mobile allocation in that band.
        </p>
      </section>

      <section>
        <h2>Frequency bands</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Band</th>
                <th>Kind</th>
                <th>National use</th>
                <th className="num">Stations</th>
                <th className="num">Notices</th>
                <th className="num">Cases</th>
                <th>Worst margin</th>
                <th>Worst notice</th>
                <th>Rule</th>
              </tr>
            </thead>
            <tbody>
              {usage.bands.map((b) => (
                <tr key={b.band + b.kind}>
                  <td className="strong">{b.band}</td>
                  <td>{b.kind}</td>
                  <td>{useWord[b.nationalUse] ?? b.nationalUse}</td>
                  <td className="num">{count(b.stations)}</td>
                  <td className="num">{count(b.notices)}</td>
                  <td className="num">{count(b.cases)}</td>
                  <td>{margin(b.worstMarginDb, limitWord(b.kind))}</td>
                  <td>{b.worstNoticeKey && <Ref to={noticeRef(b.worstNoticeKey)}>{b.worstNoticeName}</Ref>}</td>
                  <td>{b.worstRuleId}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Most affected Finnish stations</h2>
        <p>
          {allStations
            ? `All ${count(usage.stations.length)} stations with a case of concern.`
            : `The ${Math.min(STATIONS_SHOWN, usage.stations.length)} most affected of ${count(usage.stations.length)} stations with a case of concern, by worst margin.`}
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Station</th>
                <th>Bands</th>
                <th className="num">Notices</th>
                <th className="num">Cases</th>
                <th>Worst margin</th>
                <th>Worst notice</th>
              </tr>
            </thead>
            <tbody>
              {stations.map((s) => (
                <tr key={s.id} className="click" onClick={() => go({ view: "station", id: s.id })}>
                  <td className="strong">
                    <Ref to={stationRef(s.id)}>{s.id}</Ref>
                  </td>
                  <td>{s.bands.join(", ")}</td>
                  <td className="num">{count(s.notices)}</td>
                  <td className="num">{count(s.cases)}</td>
                  <td>{margin(s.worstMarginDb)}</td>
                  <td>{s.worstNoticeKey && <Ref to={noticeRef(s.worstNoticeKey)}>{s.worstNoticeName}</Ref>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {usage.stations.length > STATIONS_SHOWN && (
          <button className="plain" onClick={() => setAllStations(!allStations)}>
            {allStations ? "Show fewer" : `Show all ${count(usage.stations.length)} stations`}
          </button>
        )}
      </section>
    </div>
  );
}
