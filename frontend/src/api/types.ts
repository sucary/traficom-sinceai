// Contract between the UI and the assessment backend.
// See docs/FRONTEND_API.md for the HTTP form of every call.

import type { Assessment } from "../data";

/**
 * A reference to something the UI can open. Used in links inside any text
 * (chat answers, notifications, letters) and in navigation actions.
 *
 *   notice:<issueId>:<noticeId>     a notice of concern, e.g. notice:ific3074:124545403
 *   administration:<code>           e.g. administration:CHN
 *   station:<stationNumber>         a Finnish station, e.g. station:989011
 *   issue:<issueId>                 e.g. issue:ific3074
 *   letter:notice:<issueId>:<id>    draft letter for one notice
 *   letter:administration:<code>    draft letter for one administration
 *   chat:<conversationId>           a saved conversation
 */
export type EntityRef = string;

export interface Reference {
  ref: EntityRef;
  label: string;
}

/** One reasoning step the assistant shows before or while answering. */
export interface ReasoningStep {
  text: string; // may contain [label](ref) links
}

/** Something the assistant proposes the user opens next. */
export interface ChatAction {
  label: string;
  ref: EntityRef;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  /** Markdown subset: paragraphs, "- " lists, **bold**, [label](ref) links. */
  content: string;
  reasoning?: ReasoningStep[];
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

/**
 * Events streamed by the chat endpoint, one JSON object per line (NDJSON).
 * The UI applies them in order to the assistant message being written.
 */
export type ChatEvent =
  | { type: "reasoning"; text: string }
  | { type: "text"; text: string } // appended to content
  | { type: "reference"; ref: EntityRef; label: string }
  | { type: "action"; ref: EntityRef; label: string; auto?: boolean } // auto: open immediately
  | { type: "done" }
  | { type: "error"; message: string };

export interface ChatRequest {
  conversationId: string;
  messages: { role: "user" | "assistant"; content: string }[];
  /** What the user is looking at, so the assistant can resolve "this notice". */
  context?: { ref?: EntityRef; issueId?: string };
}

export interface Notification {
  id: string;
  text: string; // may contain [label](ref) links
  ref?: EntityRef; // where the whole notification leads
  createdAt?: string;
}

export interface LetterRequest {
  scope: "notice" | "administration";
  key: string;
}

export interface AssessmentApi {
  /** Human readable name of the backend in use, shown nowhere, used for debugging. */
  readonly name: string;
  getAssessment(): Promise<Assessment>;
  getNotifications(): Promise<Notification[]>;
  draftLetter(req: LetterRequest): Promise<string>;
  /** Streams answer events. Abort with the signal to stop generation. */
  chat(req: ChatRequest, onEvent: (e: ChatEvent) => void, signal: AbortSignal): Promise<void>;
}
