
import type { Assessment } from "../data";

export type EntityRef = string;

export interface Reference {
  ref: EntityRef;
  label: string;
}

export interface ReasoningStep {
  text: string;
}

export interface ChatAction {
  label: string;
  ref: EntityRef;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoning?: ReasoningStep[];
  thinking?: string;
  references?: Reference[];
  actions?: ChatAction[];
  status?: "streaming" | "done" | "error" | "stopped";
  error?: string;
  createdAt: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: number;
}

export type ChatEvent =
  | { type: "reasoning"; text: string }
  | { type: "thinking"; text: string }
  | { type: "text"; text: string }
  | { type: "reference"; ref: EntityRef; label: string }
  | { type: "action"; ref: EntityRef; label: string; auto?: boolean }
  | { type: "done" }
  | { type: "error"; message: string };

export interface ChatRequest {
  conversationId: string;
  messages: { role: "user" | "assistant"; content: string }[];
  context?: { ref?: EntityRef; issueId?: string };
}

export interface Notification {
  id: string;
  text: string;
  ref?: EntityRef;
  createdAt?: string;
}

export interface LetterRequest {
  scope: "notice" | "administration";
  key: string;
}

export interface UploadedFile {
  file: string;
  kind: "space" | "terrestrial";
  issue: number;
  originalName: string;
  bytes: number;
}

export interface AnalysisJob {
  id: string;
  status: "running" | "completed" | "failed";
  files: {
    file: string;
    kind: string;
    issue: number;
    status: "queued" | "running" | "completed" | "failed";
    counts: Record<string, number> | null;
    error: string | null;
  }[];
  exported: boolean;
  error: string | null;
}

export interface AssessmentApi {
  readonly name: string;
  getAssessment(): Promise<Assessment>;
  getNotifications(): Promise<Notification[]>;
  draftLetter(req: LetterRequest): Promise<string>;
  chat(req: ChatRequest, onEvent: (e: ChatEvent) => void, signal: AbortSignal): Promise<void>;
  uploadFile?(file: File, onProgress: (fraction: number) => void): Promise<UploadedFile>;
  startAnalysis?(files: string[]): Promise<AnalysisJob>;
  getAnalysis?(id: string): Promise<AnalysisJob>;
}
