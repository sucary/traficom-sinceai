import type { Assessment } from "../data";
import type {
  AnalysisJob,
  AssessmentApi,
  ChatEvent,
  ChatRequest,
  LetterRequest,
  Notification,
  UploadedFile,
} from "./types";

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.error === "string") return body.error;
  } catch {
    return `${res.status} ${res.statusText}`;
  }
  return `${res.status} ${res.statusText}`;
}

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

    uploadFile: (file: File, onProgress: (fraction: number) => void) =>
      new Promise<UploadedFile>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", url(`/uploads?name=${encodeURIComponent(file.name)}`));
        xhr.setRequestHeader("Content-Type", "application/octet-stream");
        xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
        xhr.onload = () => {
          let body: { error?: string } & Partial<UploadedFile> = {};
          try {
            body = JSON.parse(xhr.responseText);
          } catch {
            body = {};
          }
          if (xhr.status === 200) resolve(body as UploadedFile);
          else reject(new Error(body.error ?? `${xhr.status} ${xhr.statusText}`));
        };
        xhr.onerror = () => reject(new Error("The upload could not reach the backend."));
        xhr.send(file);
      }),

    async startAnalysis(files: string[]) {
      const res = await fetch(url("/analyses"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files }),
      });
      if (!res.ok) throw new Error(await errorText(res));
      return (await res.json()) as AnalysisJob;
    },

    async getAnalysis(id: string) {
      const res = await fetch(url(`/analyses/${encodeURIComponent(id)}`));
      if (!res.ok) throw new Error(await errorText(res));
      return (await res.json()) as AnalysisJob;
    },

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
