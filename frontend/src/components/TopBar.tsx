import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Notification } from "../api/types";
import { refToRoute } from "../links";
import { Route, go, href } from "../router";
import { InlineText } from "./RichText";
import { UploadPanel } from "./UploadPanel";
import { uploadsAvailable, useUploads } from "../uploadStore";

export function TopBar({ route, embedded = false }: { route: Route; embedded?: boolean }) {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [read, setRead] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const uploadRef = useRef<HTMLDivElement>(null);
  const uploads = useUploads();
  const working = uploads.phase === "uploading" || uploads.phase === "analysing";
  const failed = uploads.phase === "done" && (!!uploads.jobError || uploads.items.some((i) => i.status === "failed"));
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

  useEffect(() => {
    if (!uploadOpen) return;
    const close = (e: MouseEvent) => {
      if (uploadRef.current && !uploadRef.current.contains(e.target as Node)) setUploadOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setUploadOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [uploadOpen]);

  useEffect(() => {
    setOpen(false);
    setUploadOpen(false);
  }, [route]);

  const inChat = route.view === "chat";
  const inUsage = route.view === "usage";

  return (
    <header className={"topbar" + (embedded ? " embedded" : "")}>
      <div className={embedded ? "topbar-inner" : "page"}>
        <nav className="mainnav" aria-label="Main">
          <a href={href({ view: "home" })} aria-current={!inChat && !inUsage ? "page" : undefined}>
            Overview
          </a>
          <a href={href({ view: "chat" })} aria-current={inChat ? "page" : undefined}>
            Ask
          </a>
        </nav>
        <div className="topbar-actions">
        {uploadsAvailable() && (
          <div className="notify" ref={uploadRef}>
            <button className="plain" aria-expanded={uploadOpen} onClick={() => setUploadOpen(!uploadOpen)}>
              {working ? "Analysing" : failed ? "Analysis failed" : uploads.phase === "done" ? "Analysis done" : "Upload"}
            </button>
            {uploadOpen && <UploadPanel />}
          </div>
        )}
        <div className="notify" ref={ref}>
          <button className="plain" aria-expanded={open} onClick={() => setOpen(!open)}>
            Notifications
            {unread > 0 && <span className="count">{unread}</span>}
          </button>
          {open && (
            <div className="panel" role="dialog" aria-label="Notifications">
              <div className="panel-head">
                <h3>Notifications</h3>
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
      </div>
    </header>
  );
}
