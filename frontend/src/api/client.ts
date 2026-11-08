import { localApi } from "./local";
import { remoteApi } from "./remote";
import type { AssessmentApi } from "./types";

const base = import.meta.env.VITE_API_URL as string | undefined;

export const api: AssessmentApi = base ? remoteApi(base) : localApi;
