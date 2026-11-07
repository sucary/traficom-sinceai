import { Notice } from "../data";
import { StationTable } from "../components/StationTable";
import { Ref } from "../components/RichText";
import { noticeRef } from "../links";
import { BackIcon } from "../components/Icons";

/** Every case (space) or assessment point (terrestrial) of one notice. */
export function CasesPage({ notice }: { notice: Notice }) {
  const space = notice.kind === "Space";
  return (
    <div className="page">
      <div className="detail-head">
        <button className="plain back-btn" onClick={() => history.back()}>
          <BackIcon />
          Back
        </button>
        <h1>
          {space ? "All cases" : "All assessment points"} for{" "}
          <Ref to={noticeRef(notice.key)}>{notice.name}</Ref>
        </h1>
      </div>
      <section>
        <StationTable notice={notice} />
      </section>
    </div>
  );
}
