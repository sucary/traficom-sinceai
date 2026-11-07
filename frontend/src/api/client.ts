// Picks the backend. Set VITE_API_URL (for example in frontend/.env.local:
// VITE_API_URL=http://localhost:8000/api) to use the real backend; without it the
// UI runs on the exported results with the local stand-in.
import { localApi } from "./local";
import { remoteApi } from "./remote";
import type { AssessmentApi } from "./types";

const base = import.meta.env.VITE_API_URL as string | undefined;

export const api: AssessmentApi = base ? remoteApi(base) : localApi;
