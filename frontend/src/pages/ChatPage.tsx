import { FormEvent, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ChatAction, ChatMessage, EntityRef } from "../api/types";
import {
  addMessage,
  createConversation,
  deleteConversation,
  getConversation,
  newId,
  removeMessagesFrom,
  takeQueuedQuestion,
  updateMessage,
  useConversations,
} from "../chatStore";
import { GoIcon, SendIcon, StopIcon } from "../components/Icons";
import { RichText } from "../components/RichText";
import { refHref, refToRoute } from "../links";
import { go } from "../router";

const SUGGESTIONS = [
  "Which notices need attention first?",
  "Summarise the notices from China",
  "What does the worst notice exceed?",
  "Draft a letter to the Russian Federation",
];

async function runAnswer(
  conversationId: string,
  assistantId: string,
  context: EntityRef | undefined,
  controllers: Map<string, AbortController>,
) {
  const conv = getConversation(conversationId);
  if (!conv) return;
  const history = conv.messages
    .filter((m) => m.id !== assistantId && m.status !== "error")
    .map((m) => ({ role: m.role, content: m.content }));

  const ctrl = new AbortController();
  controllers.set(assistantId, ctrl);
  let autoAction: ChatAction | null = null;

  try {
    await api.chat({ conversationId, messages: history, context: context ? { ref: context } : undefined }, (e) => {
      updateMessage(conversationId, assistantId, (m) => {
        switch (e.type) {
          case "reasoning":
            return m;
          case "thinking":
            return { ...m, thinking: (m.thinking ?? "") + e.text };
          case "text":
            return { ...m, content: m.content + e.text };
          case "reference":
            return { ...m, references: [...(m.references ?? []), { ref: e.ref, label: e.label }] };
          case "action":
            if (e.auto && !autoAction) autoAction = e;
            return { ...m, actions: [...(m.actions ?? []), { ref: e.ref, label: e.label }] };
          case "done":
            return { ...m, status: "done" };
          case "error":
            return { ...m, status: "error", error: e.message };
        }
      });
    }, ctrl.signal);
    updateMessage(conversationId, assistantId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
    const target = autoAction as ChatAction | null;
    if (target && getConversation(conversationId)?.messages.find((m) => m.id === assistantId)?.status === "done") {
      const r = refToRoute(target.ref);
      if (r) go(r);
    }
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === "AbortError";
    updateMessage(conversationId, assistantId, (m) => ({
      ...m,
      status: aborted ? "stopped" : "error",
      error: aborted ? undefined : err instanceof Error ? err.message : String(err),
    }));
  } finally {
    controllers.delete(assistantId);
  }
}

function Composer({
  onSend,
  onStop,
  busy,
  initial = "",
  large,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  busy: boolean;
  initial?: string;
  large?: boolean;
}) {
  const [text, setText] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => ref.current?.focus(), []);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const q = text.trim();
    if (!q || busy) return;
    onSend(q);
    setText("");
  }

  function key(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form className={"composer" + (large ? " large" : "")} onSubmit={submit}>
      <div className="composer-field">
        <textarea
          ref={ref}
          rows={1}
          aria-label="Message"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={key}
        />
        {busy ? (
          <button type="button" className="round-btn" aria-label="Stop" title="Stop" onClick={onStop}>
            <StopIcon />
          </button>
        ) : (
          <button type="submit" className="round-btn" aria-label="Send" title="Send" disabled={!text.trim()}>
            <SendIcon />
          </button>
        )}
      </div>
    </form>
  );
}

function Thinking({ text, active }: { text: string; active: boolean }) {
  return (
    <details className="reasoning">
      <summary>{active ? "Thinking" : "Thought process"}</summary>
      <p className="thinking-text">{text}</p>
    </details>
  );
}

function AssistantMessage({
  m,
  last,
  onRetry,
}: {
  m: ChatMessage;
  last: boolean;
  onRetry: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const streaming = m.status === "streaming";
  return (
    <div className="msg ai">
      {m.thinking && <Thinking text={m.thinking} active={streaming && !m.content} />}
      {m.content ? <RichText text={m.content} /> : streaming && !m.thinking && <p className="thinking">Thinking</p>}
      {m.status === "error" && (
        <p className="strong">The answer could not be completed. {m.error}</p>
      )}
      {m.status === "stopped" && <p className="strong">Stopped</p>}

      {m.references && m.references.length > 0 && (
        <details className="reasoning refs">
          <summary>Sources ({m.references.length})</summary>
          <ul>
            {m.references.map((r) => {
              const h = refHref(r.ref);
              const external = h?.startsWith("http");
              return (
                <li key={r.ref + r.label}>
                  {h ? (
                    <a className="ref" href={h} target={external ? "_blank" : undefined} rel="noreferrer">
                      {r.label}
                    </a>
                  ) : (
                    r.label
                  )}
                </li>
              );
            })}
          </ul>
        </details>
      )}

      {m.actions && m.actions.length > 0 && (
        <div className="chat-actions">
          {m.actions.map((a) => (
            <button
              key={a.ref + a.label}
              className="go-btn"
              onClick={() => {
                const r = refToRoute(a.ref);
                if (r) go(r);
              }}
            >
              <GoIcon />
              {a.label}
            </button>
          ))}
        </div>
      )}

      {!streaming && (
        <div className="msg-tools">
          <button
            className="plain"
            onClick={() => {
              navigator.clipboard?.writeText(m.content);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? "Copied" : "Copy"}
          </button>
          {last && (
            <button className="plain" onClick={onRetry}>
              {m.status === "error" ? "Retry" : "Regenerate"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatPage({ conversationId, header }: { conversationId?: string; header?: ReactNode }) {
  const conversations = useConversations();
  const conv = conversations.find((c) => c.id === conversationId);
  const controllers = useRef(new Map<string, AbortController>()).current;
  const [context, setContext] = useState<EntityRef | undefined>();
  const [prefill, setPrefill] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const busy = !!conv?.messages.some((m) => m.status === "streaming");

  function send(text: string, ctx = context) {
    let id = conv?.id;
    if (!id) {
      id = createConversation(text).id;
      go({ view: "chat", conversationId: id });
    }
    addMessage(id, { id: newId(), role: "user", content: text, createdAt: Date.now() });
    const assistantId = newId();
    addMessage(id, { id: assistantId, role: "assistant", content: "", status: "streaming", createdAt: Date.now() });
    runAnswer(id, assistantId, ctx, controllers);
  }

  function stop() {
    controllers.forEach((c) => c.abort());
  }

  function retry(m: ChatMessage) {
    if (!conv) return;
    removeMessagesFrom(conv.id, m.id);
    const assistantId = newId();
    addMessage(conv.id, { id: assistantId, role: "assistant", content: "", status: "streaming", createdAt: Date.now() });
    runAnswer(conv.id, assistantId, context, controllers);
  }

  useEffect(() => {
    const q = takeQueuedQuestion();
    if (q) {
      setContext(q.ref);
      setPrefill(q.question);
    }
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [conv?.messages.length, conv?.messages[conv.messages.length - 1]?.content.length]);

  useEffect(() => () => controllers.forEach((c) => c.abort()), [controllers]);

  const empty = !conv || conv.messages.length === 0;
  const lastAssistant = conv?.messages.filter((m) => m.role === "assistant").slice(-1)[0];

  return (
    <div className="chat-layout">
      <aside className="chat-side">
        <button className="new-chat" onClick={() => go({ view: "chat" })}>New chat</button>
        <nav aria-label="Conversations">
          {conversations.map((c) => (
            <div key={c.id} className={"conv" + (c.id === conversationId ? " current" : "")}>
              <a href={`#/chat/${encodeURIComponent(c.id)}`}>{c.title}</a>
              <button
                className="plain"
                aria-label={`Delete ${c.title}`}
                onClick={() => {
                  deleteConversation(c.id);
                  if (c.id === conversationId) go({ view: "chat" });
                }}
              >
                Delete
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <div className="chat-main">
        {header}
        {empty ? (
          <div className="chat-empty">
            <h1>Ask about interference risks</h1>
            <Composer
              key={(conversationId ?? "new") + prefill}
              initial={prefill}
              onSend={(text) => {
                setPrefill("");
                send(text);
              }}
              onStop={stop}
              busy={busy}
              large
            />
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="plain" onClick={() => setPrefill(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="thread" aria-live="polite">
              {conv!.messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="msg user">
                    {m.content}
                  </div>
                ) : (
                  <AssistantMessage key={m.id} m={m} last={m.id === lastAssistant?.id} onRetry={() => retry(m)} />
                ),
              )}
              <div ref={endRef} />
            </div>
            <div className="composer-dock">
              <Composer key={conversationId} onSend={send} onStop={stop} busy={busy} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
