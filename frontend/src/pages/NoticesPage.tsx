import { Assessment } from "../data";
import { NoticeList } from "../components/NoticeList";
import { BackIcon } from "../components/Icons";

export function NoticesPage({
  data,
  scope,
  keyValue,
}: {
  data: Assessment;
  scope: "issue" | "administration";
  keyValue: string;
}) {
  const notices =
    scope === "issue"
      ? data.notices.filter((n) => n.issueId === keyValue)
      : data.notices.filter((n) => n.administration === keyValue);
  const title =
    scope === "issue"
      ? data.issues.find((i) => i.id === keyValue)?.label ?? keyValue
      : notices[0]?.administrationName ?? keyValue;

  return (
    <div className="page">
      <div className="detail-head">
        <button className="plain back-btn" onClick={() => history.back()}>
          <BackIcon />
          Back
        </button>
        <h1>Notices of concern in {title}</h1>
      </div>
      <section>
        {notices.length ? <NoticeList notices={notices} /> : <p>No notices of concern.</p>}
      </section>
    </div>
  );
}
