import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Assessment } from "../data";
import { lettersFor } from "../letters";
import { noticeRef } from "../links";
import { go } from "../router";
import { Ref } from "./RichText";

export function Letter({
  data,
  scope,
  keyValue,
}: {
  data: Assessment;
  scope: "notice" | "administration";
  keyValue: string;
}) {
  const administrations = useMemo(
    () =>
      [...new Map(data.notices.map((n) => [n.administration, n.administrationName])).entries()].sort((a, b) =>
        a[1].localeCompare(b[1]),
      ),
    [data],
  );

  const list = lettersFor(data, scope, keyValue);

  const [text, setText] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    setState("loading");
    setCopied(false);
    api.draftLetter({ scope, key: keyValue }).then(
      (t) => {
        if (!live) return;
        setText(t);
        setState("ready");
      },
      () => live && setState("failed"),
    );
    return () => {
      live = false;
    };
  }, [scope, keyValue]);

  function download() {
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `letter_${scope}_${keyValue.replace(/\W+/g, "_")}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="page letter">
      <div className="detail-head">
        <button className="plain" onClick={() => history.back()}>
          Back
        </button>
        <h1>Draft letter</h1>
      </div>
      <section>
        <div className="controls">
          <select
            aria-label="Letter scope"
            value={`${scope}|${keyValue}`}
            onChange={(e) => {
              const [s, k] = e.target.value.split("|");
              go({ view: "letter", scope: s as "notice" | "administration", key: k });
            }}
          >
            <optgroup label="Administration">
              {administrations.map(([code, name]) => (
                <option key={code} value={`administration|${code}`}>
                  {name}
                </option>
              ))}
            </optgroup>
            <optgroup label="Notice">
              {data.notices.map((n) => (
                <option key={n.key} value={`notice|${n.key}`}>
                  {n.name} {n.noticeId}
                </option>
              ))}
            </optgroup>
          </select>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(text);
              setCopied(true);
            }}
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <button onClick={download}>Download</button>
        </div>
        {state === "loading" && <p className="thinking">Drafting</p>}
        {state === "failed" && <p className="strong">The letter could not be drafted.</p>}
        {state === "ready" && (
          <textarea aria-label="Letter text" value={text} onChange={(e) => setText(e.target.value)} />
        )}
        {list.length > 0 && (
          <div className="covers">
            <h3>Notices in this letter</h3>
            <ul className="list">
              {list.map((n) => (
                <li key={n.key}>
                  <Ref to={noticeRef(n.key)}>{n.name}</Ref> {n.noticeId}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
