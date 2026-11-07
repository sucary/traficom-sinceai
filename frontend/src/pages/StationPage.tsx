import { Assessment, label, noticesForStation } from "../data";
import { coord, limitWord, margin, num } from "../format";
import { queueQuestion } from "../chatStore";
import { Ref } from "../components/RichText";
import { adminRef, noticeRef, stationRef } from "../links";
import { go } from "../router";
import { BackIcon } from "../components/Icons";

export function StationPage({ data, id }: { data: Assessment; id: string }) {
  const notices = noticesForStation(data, id);
  const rows = notices.flatMap((n) => n.stations.filter((s) => s.id === id).map((s) => ({ n, s })));
  rows.sort((a, b) => (a.s.marginDb ?? 99) - (b.s.marginDb ?? 99));
  const first = rows[0]?.s;

  return (
    <div className="page">
      <div className="detail-head">
        <button className="plain back-btn" onClick={() => history.back()}>
          <BackIcon />
          Back
        </button>
        <h1>Station {id}</h1>
      </div>

      <section>
        <dl className="facts">
          <div>
            <dt>Notices of concern</dt>
            <dd>{notices.length}</dd>
          </div>
          <div>
            <dt>Cases of concern</dt>
            <dd>{rows.length}</dd>
          </div>
          {first && (
            <div>
              <dt>Location</dt>
              <dd>{coord(first.latitude, first.longitude)}</dd>
            </div>
          )}
          {first && (
            <div>
              <dt>Worst margin</dt>
              <dd>{margin(first.marginDb)}</dd>
            </div>
          )}
        </dl>
        <div className="actions detail-actions">
          <button
            onClick={() => {
              queueQuestion(`Which notices affect station ${id}?`, stationRef(id));
              go({ view: "chat" });
            }}
          >
            Ask about this station
          </button>
        </div>
      </section>

      <section>
        <h2>Notices affecting this station</h2>
        {rows.length === 0 ? (
          <p>No notice of concern affects this station.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Satellite or station</th>
                  <th>Administration</th>
                  <th>Protected band</th>
                  <th>Status</th>
                  <th className="num">Value</th>
                  <th className="num">Limit</th>
                  <th className="num">Margin</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ n, s }, i) => (
                  <tr key={n.key + i} className="click" onClick={() => go({ view: "notice", key: n.key })}>
                    <td className="strong">
                      <Ref to={noticeRef(n.key)}>{n.name}</Ref>
                    </td>
                    <td>
                      <Ref to={adminRef(n.administration)}>{n.administrationName}</Ref>
                    </td>
                    <td className="nowrap">{s.band}</td>
                    <td className="nowrap">{label(s.status)}</td>
                    <td className="num">{num(s.value)}</td>
                    <td className="num">{num(s.limit)}</td>
                    <td className="num">{margin(s.marginDb, limitWord(n.kind))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
