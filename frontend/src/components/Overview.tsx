import { Issue } from "../data";
import { count } from "../format";
import { go } from "../router";

export function Overview({ issue }: { issue: Issue }) {
  return (
    <>
      <div className="stats">
        <div className="stat lead">
          <strong>{count(issue.noticesOfConcern)}</strong>
          Notices of concern
        </div>
        {(issue.highlights ?? []).map((h) => (
          <div className="stat" key={h.label}>
            <strong>{count(h.value ?? 0)}</strong>
            {h.label}
          </div>
        ))}
        <button className="stat impact-link" onClick={() => go({ view: "usage", issueId: issue.id })}>
          <span>Impact on Finnish use</span>
          <span className="impact-arrow" aria-hidden="true">→</span>
        </button>
      </div>
    </>
  );
}
