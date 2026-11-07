import { Assessment } from "../data";
import { queueQuestion } from "../chatStore";
import { NoticeList } from "../components/NoticeList";
import { adminRef } from "../links";
import { go } from "../router";
import { BackIcon } from "../components/Icons";

export function AdministrationPage({ data, code }: { data: Assessment; code: string }) {
  const notices = data.notices.filter((n) => n.administration === code);
  const name = notices[0]?.administrationName ?? code;
  const stations = new Set(notices.flatMap((n) => n.stations.filter((s) => /^\d+$/.test(s.id)).map((s) => s.id)));
  const exceeding = notices.filter((n) => n.status.startsWith("exceeds")).length;

  return (
    <div className="page">
      <div className="detail-head">
        <button className="plain back-btn" onClick={() => history.back()}>
          <BackIcon />
          Back
        </button>
        <h1>
          {name} ({code})
        </h1>
      </div>

      <section>
        <div className="stats">
          <div className="stat">
            <strong>{notices.length}</strong>
            Notices of concern
          </div>
          <div className="stat">
            <strong>{exceeding}</strong>
            Exceeding
          </div>
          <div className="stat">
            <strong>{stations.size}</strong>
            Finnish stations involved
          </div>
        </div>
        <div className="actions detail-actions">
          <button onClick={() => go({ view: "letter", scope: "administration", key: code })}>
            Draft letter for {name}
          </button>
          <button
            className="plain"
            onClick={() => {
              queueQuestion(`Summarise the notices from ${name}`, adminRef(code));
              go({ view: "chat" });
            }}
          >
            Ask about {name}
          </button>
        </div>
      </section>

      <section>
        <h2>Notices</h2>
        {notices.length ? (
          <NoticeList notices={notices} limit={15} full={{ view: "notices", scope: "administration", key: code }} />
        ) : (
          <p>No notices of concern from {name}.</p>
        )}
      </section>
    </div>
  );
}
