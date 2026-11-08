import { useRef } from "react";
import {
  UploadItem,
  removeFile,
  selectFiles,
  uploadAndAnalyse,
  useUploads,
} from "../uploadStore";

const issueLabel = (item: UploadItem) =>
  item.uploaded ? `${item.uploaded.kind === "space" ? "IFIC" : "BR IFIC"} ${item.uploaded.issue}` : "";

function statusText(item: UploadItem) {
  switch (item.status) {
    case "selected":
      return `${(item.size / 1024 / 1024).toFixed(1)} MB`;
    case "uploading":
      return `Uploading ${Math.round(item.progress * 100)}%`;
    case "uploaded":
    case "queued":
      return `${issueLabel(item)} waiting`;
    case "running":
      return `${issueLabel(item)} calculating, this can take a few minutes`;
    case "completed":
      return `${issueLabel(item)} analysis successfully completed`;
    case "failed":
      return item.error ?? "Failed";
  }
}

export function UploadPanel() {
  const { items, phase, jobError, resultIssue } = useUploads();
  const input = useRef<HTMLInputElement>(null);
  const busy = phase === "uploading" || phase === "analysing";

  return (
    <div className="panel upload-panel" role="dialog" aria-label="Analyse IFIC files">
      <div className="panel-head">
        <h3>Analyse IFIC files</h3>
        {!busy && (
          <button className="small" onClick={() => input.current?.click()}>
            Choose files
          </button>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept=".mdb"
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files) selectFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {items.length === 0 ? (
        <p className="upload-item">Space IFIC or terrestrial BR IFIC .mdb databases</p>
      ) : (
        items.map((item) => (
          <div className="upload-item" key={item.id}>
            <div className="upload-row">
              <span className="strong upload-name">{item.name}</span>
              {phase === "idle" && (
                <button className="plain small" onClick={() => removeFile(item.id)}>
                  Remove
                </button>
              )}
            </div>
            <div>{statusText(item)}</div>
            {item.status === "uploading" && (
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${item.progress * 100}%` }} />
              </div>
            )}
          </div>
        ))
      )}
      {jobError && <p className="upload-item">{jobError}</p>}
      <div className="upload-actions">
        {phase === "done" && resultIssue ? (
          <button
            className="primary"
            onClick={() => {
              window.location.hash = `#/issue/${resultIssue}`;
              window.location.reload();
            }}
          >
            Show results
          </button>
        ) : (
          <button className="primary" disabled={busy || items.length === 0} onClick={() => uploadAndAnalyse()}>
            {phase === "uploading" ? "Uploading" : phase === "analysing" ? "Calculating" : "Upload and analyse"}
          </button>
        )}
      </div>
    </div>
  );
}
