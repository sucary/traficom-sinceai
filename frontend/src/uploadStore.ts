import { useSyncExternalStore } from "react";
import { api } from "./api/client";
import type { AnalysisJob, UploadedFile } from "./api/types";

export interface UploadItem {
  id: string;
  name: string;
  size: number;
  file: File;
  progress: number;
  uploaded?: UploadedFile;
  status: "selected" | "uploading" | "uploaded" | "queued" | "running" | "completed" | "failed";
  error?: string;
  counts?: Record<string, number> | null;
}

export interface UploadState {
  items: UploadItem[];
  phase: "idle" | "uploading" | "analysing" | "done";
  jobError?: string;
  resultIssue?: string;
}

const listeners = new Set<() => void>();
let state: UploadState = { items: [], phase: "idle" };

function set(next: Partial<UploadState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function setItem(id: string, change: Partial<UploadItem>) {
  set({ items: state.items.map((i) => (i.id === id ? { ...i, ...change } : i)) });
}

export function useUploads(): UploadState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
  );
}

export const uploadsAvailable = () => typeof api.uploadFile === "function";

export function selectFiles(files: FileList | File[]) {
  if (state.phase === "uploading" || state.phase === "analysing") return;
  const kept = state.phase === "done" ? [] : state.items;
  const added = [...files]
    .filter((f) => f.name.toLowerCase().endsWith(".mdb"))
    .map((f, i) => ({ id: `${Date.now()}-${i}-${f.name}`, name: f.name, size: f.size, file: f, progress: 0,
                      status: "selected" as const }));
  set({ items: [...kept, ...added], phase: "idle", jobError: undefined, resultIssue: undefined });
}

export function removeFile(id: string) {
  if (state.phase !== "idle") return;
  set({ items: state.items.filter((i) => i.id !== id) });
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function applyJob(job: AnalysisJob) {
  set({
    items: state.items.map((item) => {
      const f = job.files.find((x) => x.file === item.uploaded?.file);
      return f ? { ...item, status: f.status, error: f.error ?? undefined, counts: f.counts } : item;
    }),
  });
}

export async function uploadAndAnalyse() {
  if (!api.uploadFile || !api.startAnalysis || !api.getAnalysis) return;
  if (state.phase === "done") {
    set({
      items: state.items
        .filter((i) => i.status !== "completed")
        .map((i) => ({ ...i, status: "selected", progress: 0, uploaded: undefined, error: undefined, counts: undefined })),
      phase: "idle",
      jobError: undefined,
      resultIssue: undefined,
    });
  }
  if (state.phase !== "idle" || state.items.length === 0) return;
  set({ phase: "uploading", jobError: undefined });
  for (const item of state.items) {
    if (item.uploaded) continue;
    setItem(item.id, { status: "uploading", progress: 0 });
    try {
      const uploaded = await api.uploadFile(item.file, (p) => setItem(item.id, { progress: p }));
      setItem(item.id, { status: "uploaded", progress: 1, uploaded });
    } catch (error) {
      setItem(item.id, { status: "failed", error: (error as Error).message });
    }
  }
  const files = [...new Set(state.items.filter((i) => i.uploaded).map((i) => i.uploaded!.file))];
  if (files.length === 0) {
    set({ phase: "done", jobError: "No file could be uploaded." });
    return;
  }
  set({ phase: "analysing" });
  try {
    let job = await api.startAnalysis(files);
    applyJob(job);
    while (job.status === "running") {
      await wait(2000);
      job = await api.getAnalysis(job.id);
      applyJob(job);
    }
    const done = job.files.filter((f) => f.status === "completed");
    const last = done[done.length - 1];
    set({
      phase: "done",
      jobError: job.error ?? undefined,
      resultIssue: last ? last.file.replace(/\.mdb$/i, "").toLowerCase() : undefined,
    });
  } catch (error) {
    set({ phase: "done", jobError: (error as Error).message });
  }
}
