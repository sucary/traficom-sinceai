import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Notification } from "../api/types";
import { refToRoute } from "../links";
import { Route, go, href } from "../router";
import { InlineText } from "./RichText";

export function TopBar({ route }: { route: Route }) {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [read, setRead] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);
  const unread = items.filter((n) => !read.has(n.id)).length;

  useEffect(() => {
    api.getNotifications().then(setItems, () => setItems([]));
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  // Following any link inside the panel closes it.
  useEffect(() => setOpen(false), [route]);

  const inChat = route.view === "chat";

  return (
    <header className="topbar">
      <div className="page">
        <nav className="mainnav" aria-label="Main">
          <a className="brand" href={href({ view: "home" })}>
            Traficom Assessment
          </a>
          <a href={href({ view: "home" })} aria-current={!inChat ? "page" : undefined}>
            Overview
          </a>
          <a href={href({ view: "chat" })} aria-current={inChat ? "page" : undefined}>
            Chat
          </a>
        </nav>
        <div className="notify" ref={ref}>
          <button className="plain" aria-expanded={open} onClick={() => setOpen(!open)}>
            Notifications
            {unread > 0 && <span className="count">{unread}</span>}
          </button>
          {open && (
            <div className="panel" role="dialog" aria-label="Notifications">
              <div className="panel-head">
                <h3>Notifications</h3>
                {unread > 0 && (
                  <button className="plain" onClick={() => setRead(new Set(items.map((i) => i.id)))}>
                    Mark all read
                  </button>
                )}
              </div>
              {items.length === 0 && <p className="item">No notifications</p>}
              {items.map((n) => (
                <div
                  key={n.id}
                  className={"item" + (read.has(n.id) ? "" : " unread")}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    setRead(new Set(read).add(n.id));
                    const r = n.ref ? refToRoute(n.ref) : null;
                    if (r) go(r);
                  }}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    setRead(new Set(read).add(n.id));
                    const r = n.ref ? refToRoute(n.ref) : null;
                    if (r) go(r);
                  }}
                >
                  <InlineText text={n.text} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
