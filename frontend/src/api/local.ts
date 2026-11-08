import type { Assessment, Notice } from "../data";
import { label } from "../data";
import { limitWord, margin } from "../format";
import { templateLetter } from "../letters";
import { adminRef, noticeRef, stationRef } from "../links";
import type { AssessmentApi, ChatEvent, ChatRequest, Notification } from "./types";

let data: Promise<Assessment> | null = null;

function load(): Promise<Assessment> {
  data ??= fetch(`${import.meta.env.BASE_URL}data/assessment.json`).then((r) => {
    if (!r.ok) throw new Error("No exported results found");
    return r.json();
  });
  return data;
}

const link = (text: string, ref: string) => `[${text}](${ref})`;
const nlink = (n: Notice) => link(n.name, noticeRef(n.key));
const alink = (n: Notice) => link(n.administrationName, adminRef(n.administration));
const mg = (n: Notice) => margin(n.worstMarginDb, limitWord(n.kind));

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

interface Plan {
  reasoning: string[];
  answer: string;
  references: { ref: string; label: string }[];
  actions: { ref: string; label: string; auto?: boolean }[];
}

function noticeAnswer(d: Assessment, n: Notice): Plan {
  const issue = d.issues.find((i) => i.id === n.issueId);
  const top = n.stations.slice(0, 3);
  const stationWord = n.kind === "Space" ? "Finnish stations" : "assessment points";
  return {
    reasoning: [
      `Matched ${nlink(n)} (notice ${n.noticeId}) in ${issue ? link(issue.label, `issue:${issue.id}`) : n.issueId}.`,
      `Read the worst case: ${label(n.status)}, ${mg(n)}.`,
      `Checked ${n.stations.length} ${stationWord} and the governing rule ${n.rule.id}.`,
    ],
    answer: [
      `${nlink(n)} from ${alink(n)} is marked **${label(n.status)}** with a worst margin of **${mg(n)}**, affecting ${n.stationsAffected} Finnish stations.`,
      top.length
        ? `The worst ${stationWord} are\n` +
          top
            .map((s) => `- ${/^\d+$/.test(s.id) ? link(s.id, stationRef(s.id)) : s.id}, ${s.band}, ${margin(s.marginDb, limitWord(n.kind))}`)
            .join("\n")
        : "",
      `The governing rule is ${n.rule.id}, ${n.citation.provision}${n.citation.printedPage ? `, printed page ${n.citation.printedPage}` : ""}.`,
      `This is a pessimistic screening value and a reason for expert review, not proof of harmful interference.`,
    ]
      .filter(Boolean)
      .join("\n\n"),
    references: [
      { ref: noticeRef(n.key), label: `${n.name} notice ${n.noticeId}` },
      ...(n.citation.url ? [{ ref: n.citation.url, label: n.citation.document }] : []),
    ],
    actions: [
      { ref: noticeRef(n.key), label: `Open ${n.name}` },
      { ref: `letter:notice:${n.key}`, label: "Draft letter for this notice" },
      { ref: adminRef(n.administration), label: `All notices from ${n.administrationName}` },
    ],
  };
}

function adminAnswer(d: Assessment, code: string): Plan {
  const list = d.notices.filter((n) => n.administration === code);
  const name = list[0]?.administrationName ?? code;
  return {
    reasoning: [
      `Filtered notices of concern by administration ${link(name, adminRef(code))}.`,
      `Found ${list.length} notices and ordered them by status and worst margin.`,
    ],
    answer:
      `${link(name, adminRef(code))} has **${list.length} notices of concern**. The highest priority are\n` +
      list
        .slice(0, 5)
        .map((n) => `- ${nlink(n)}, ${label(n.status).toLowerCase()}, ${mg(n)}, ${n.stationsAffected} stations`)
        .join("\n"),
    references: list.slice(0, 5).map((n) => ({ ref: noticeRef(n.key), label: n.name })),
    actions: [
      { ref: adminRef(code), label: `Open ${name}` },
      { ref: `letter:administration:${code}`, label: `Draft letter for ${name}` },
    ],
  };
}

function stationAnswer(d: Assessment, id: string): Plan {
  const list = d.notices.filter((n) => n.stations.some((s) => s.id === id));
  return {
    reasoning: [`Looked up Finnish station ${link(id, stationRef(id))} in every notice of concern.`, `Found ${list.length} notices.`],
    answer:
      `Station ${link(id, stationRef(id))} appears in **${list.length} notices of concern**.\n` +
      list
        .slice(0, 6)
        .map((n) => `- ${nlink(n)} from ${alink(n)}, ${mg(n)}`)
        .join("\n"),
    references: list.slice(0, 6).map((n) => ({ ref: noticeRef(n.key), label: n.name })),
    actions: [{ ref: stationRef(id), label: `Open station ${id}` }],
  };
}

function overviewAnswer(d: Assessment): Plan {
  const top = d.notices.slice(0, 5);
  return {
    reasoning: [
      `Read ${d.issues.map((i) => link(i.label, `issue:${i.id}`)).join(" and ")}.`,
      `Ranked ${d.notices.length} notices of concern by status, worst margin and stations affected.`,
    ],
    answer:
      d.issues
        .map((i) => `${link(i.label, `issue:${i.id}`)} has **${i.noticesOfConcern} notices of concern**.`)
        .join(" ") +
      `\n\nThe highest priority notices are\n` +
      top.map((n) => `- ${nlink(n)} from ${alink(n)}, ${mg(n)}, ${n.stationsAffected} stations`).join("\n") +
      `\n\nEvery value is a pessimistic screening result and a reason for expert review.`,
    references: top.map((n) => ({ ref: noticeRef(n.key), label: n.name })),
    actions: d.issues.map((i) => ({ ref: `issue:${i.id}`, label: `Open ${i.label}` })),
  };
}

function plan(d: Assessment, req: ChatRequest): Plan {
  const q = req.messages[req.messages.length - 1]?.content ?? "";
  const lower = q.toLowerCase();
  const words = lower.split(/[^a-z0-9.]+/);

  const ctx = req.context?.ref?.startsWith("notice:")
    ? d.notices.find((n) => noticeRef(n.key) === req.context!.ref)
    : undefined;
  const byName = d.notices.find((n) => lower.includes(n.name.toLowerCase()) || words.includes(n.noticeId));
  const notice = byName ?? (/\bthis\b/.test(lower) ? ctx : undefined);
  const wantsLetter = /\bletter\b|\bdraft\b/.test(lower);

  if (notice) {
    const p = noticeAnswer(d, notice);
    if (wantsLetter) p.actions.unshift({ ref: `letter:notice:${notice.key}`, label: "Open the draft letter", auto: true });
    return p;
  }

  const admin = d.notices.find(
    (n) => words.includes(n.administration.toLowerCase()) || lower.includes(n.administrationName.toLowerCase()),
  );
  if (admin) {
    const p = adminAnswer(d, admin.administration);
    if (wantsLetter)
      p.actions.unshift({ ref: `letter:administration:${admin.administration}`, label: "Open the draft letter", auto: true });
    return p;
  }

  const station = words.find((w) => /^\d{6}$/.test(w) && d.notices.some((n) => n.stations.some((s) => s.id === w)));
  if (station) return stationAnswer(d, station);

  return overviewAnswer(d);
}

async function localChat(req: ChatRequest, onEvent: (e: ChatEvent) => void, signal: AbortSignal) {
  const d = await load();
  const p = plan(d, req);
  for (const step of p.reasoning) {
    await sleep(350, signal);
    onEvent({ type: "reasoning", text: step });
  }
  const tokens = p.answer.match(/\S+\s*/g) ?? [];
  for (let i = 0; i < tokens.length; i += 3) {
    await sleep(25, signal);
    onEvent({ type: "text", text: tokens.slice(i, i + 3).join("") });
  }
  for (const r of p.references) onEvent({ type: "reference", ...r });
  for (const a of p.actions) onEvent({ type: "action", ...a });
  onEvent({ type: "done" });
}

async function notifications(): Promise<Notification[]> {
  const d = await load();
  const items: Notification[] = [];
  for (const issue of d.issues) {
    items.push({
      id: `ready:${issue.id}`,
      text: `${link(issue.label, `issue:${issue.id}`)} results are ready with ${issue.noticesOfConcern} notices of concern`,
      ref: `issue:${issue.id}`,
    });
    const top = d.notices.find((n) => n.issueId === issue.id);
    if (top)
      items.push({
        id: `top:${top.key}`,
        text: `${nlink(top)} from ${alink(top)} is ${mg(top)}`,
        ref: noticeRef(top.key),
      });
  }
  return items;
}

export const localApi: AssessmentApi = {
  name: "local",
  getAssessment: load,
  getNotifications: notifications,
  draftLetter: async ({ scope, key }) => templateLetter(await load(), scope, key),
  chat: localChat,
};
