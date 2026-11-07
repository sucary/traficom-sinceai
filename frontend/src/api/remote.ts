// HTTP client for the assessment backend. Contract: docs/FRONTEND_API.md
import type { Assessment } from "../data";
import type { AssessmentApi, ChatEvent, ChatRequest, LetterRequest, Notification } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function remoteApi(base: string): AssessmentApi {
  const url = (path: string) => base.replace(/\/$/, "") + path;

  return {
    name: `remote ${base}`,

    getAssessment: () => fetch(url("/assessment")).then((r) => json<Assessment>(r)),

    getNotifications: () => fetch(url("/notifications")).then((r) => json<Notification[]>(r)),

    draftLetter: (req: LetterRequest) =>
      fetch(url("/letters"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      })
        .then((r) => json<{ text: string }>(r))
        .then((r) => r.text),

    async chat(req: ChatRequest, onEvent: (e: ChatEvent) => void, signal: AbortSignal) {
      const res = await fetch(url("/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: JSON.stringify(req),
        signal,
      });
      if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, nl).trim();
          buffer = buffer.slice(nl + 1);
          if (line) onEvent(JSON.parse(line) as ChatEvent);
        }
      }
      if (buffer.trim()) onEvent(JSON.parse(buffer) as ChatEvent);
    },
  };
}
