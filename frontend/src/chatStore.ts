import { useSyncExternalStore } from "react";
import type { ChatMessage, Conversation, EntityRef } from "./api/types";

const KEY = "traficom.chat.v1";
const listeners = new Set<() => void>();
let state: Conversation[] = read();

function read(): Conversation[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Conversation[]) : [];
  } catch {
    return [];
  }
}

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    return;
  }
}

function set(next: Conversation[]) {
  state = next;
  save();
  listeners.forEach((l) => l());
}

export function useConversations(): Conversation[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
  );
}

export const newId = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

export function createConversation(title: string): Conversation {
  const c: Conversation = { id: newId(), title: title.slice(0, 80), messages: [], updatedAt: Date.now() };
  set([c, ...state]);
  return c;
}

export function getConversation(id: string | undefined) {
  return state.find((c) => c.id === id);
}

export function deleteConversation(id: string) {
  set(state.filter((c) => c.id !== id));
}

export function addMessage(id: string, message: ChatMessage) {
  set(
    state.map((c) => (c.id === id ? { ...c, messages: [...c.messages, message], updatedAt: Date.now() } : c)),
  );
}

export function updateMessage(id: string, messageId: string, change: (m: ChatMessage) => ChatMessage) {
  set(
    state.map((c) =>
      c.id === id ? { ...c, messages: c.messages.map((m) => (m.id === messageId ? change(m) : m)) } : c,
    ),
  );
}

export function removeMessagesFrom(id: string, messageId: string) {
  set(
    state.map((c) => {
      if (c.id !== id) return c;
      const i = c.messages.findIndex((m) => m.id === messageId);
      return i < 0 ? c : { ...c, messages: c.messages.slice(0, i) };
    }),
  );
}

let pending: { question: string; ref?: EntityRef } | null = null;

export function queueQuestion(question: string, ref?: EntityRef) {
  pending = { question, ref };
}

export function takeQueuedQuestion() {
  const p = pending;
  pending = null;
  return p;
}
