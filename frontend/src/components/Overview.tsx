import { Issue, label } from "../data";
import { count } from "../format";

const order = [
  "exceeds_limit",
  "exceeds_threshold",
  "near_limit",
  "near_threshold",
  "unallocated_service_rr_4_4",
  "below_limit",
  "below_threshold",
];

export function Overview({ issue }: { issue: Issue }) {
  const statuses = Object.keys(issue.counts).sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || issue.counts[b] - issue.counts[a];
  });
  return (
    <div className="stats">
      <div className="stat lead">
        <strong>{count(issue.noticesOfConcern)}</strong>
        Notices of concern
      </div>
      {statuses.map((s) => (
        <div className="stat" key={s}>
          <strong>{count(issue.counts[s])}</strong>
          {label(s)}
        </div>
      ))}
    </div>
  );
}
