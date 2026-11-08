import type { Assessment, Notice } from "./data";
import { label } from "./data";
import { limitWord, margin, withUnit } from "./format";

function today() {
  return new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function paragraph(n: Notice, i: number, issues: Assessment["issues"]) {
  const issue = issues.find((x) => x.id === n.issueId)?.label ?? n.issueId;
  const what = n.kind === "Space" ? "power flux density" : "field strength at the Finnish border";
  const head =
    n.kind === "Space"
      ? `${i}. Notice ${n.noticeId}, ${n.name}, ${n.provision}${n.publicationDate ? `, published ${n.publicationDate}` : ""}, ${issue}`
      : `${i}. Assignment ${n.noticeId}, ${n.name}, ${n.provision.toLowerCase()}, ${issue}`;
  const ref = [n.rule.id, n.citation.provision].filter(Boolean).join(", ");
  return `${head}

Our screening shows a worst case ${what} of ${withUnit(n.value, n.unit)} against a ${limitWord(n.kind)} of ${withUnit(n.limit, n.unit)}${n.referenceBandwidth ? ` in ${n.referenceBandwidth}` : ""} (${ref}). This is ${margin(n.worstMarginDb, limitWord(n.kind))} and the case is marked ${label(n.status)}. ${n.stationsAffected} Finnish stations are affected.`;
}

export function lettersFor(data: Assessment, scope: "notice" | "administration", key: string): Notice[] {
  return scope === "notice"
    ? data.notices.filter((n) => n.key === key)
    : data.notices.filter((n) => n.administration === key);
}

export function templateLetter(data: Assessment, scope: "notice" | "administration", key: string): string {
  const list = lettersFor(data, scope, key);
  if (!list.length) return "";
  const n = list[0];
  const body = list.map((x, i) => paragraph(x, i + 1, data.issues)).join("\n\n");
  return `Finnish Transport and Communications Agency Traficom
${today()}

To the Administration of ${n.administrationName} (${n.administration})

Subject: Comments on ${list.length === 1 ? "a filing" : `${list.length} filings`} published in the ITU International Frequency Information Circular

Dear Colleagues,

Traficom has reviewed the filings listed below against the protection of Finnish radio stations. The values are deterministic worst case screening results and a reason for further review, not proof of harmful interference.

${body}

We kindly ask your Administration to confirm the technical parameters of these filings and to take the protection of the Finnish stations into account. We are ready to discuss these results.

Yours sincerely,

Spectrum Management
Finnish Transport and Communications Agency Traficom`;
}
