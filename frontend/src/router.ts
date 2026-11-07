import { useEffect, useState } from "react";

export type Route =
  | { view: "home"; issueId?: string }
  | { view: "notice"; key: string }
  | { view: "letter"; scope: "notice" | "administration"; key: string }
  | { view: "chat"; conversationId?: string }
  | { view: "station"; id: string }
  | { view: "administration"; code: string }
  | { view: "stats"; id: string }
  | { view: "notices"; scope: "issue" | "administration"; key: string }
  | { view: "cases"; key: string };

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  switch (parts[0]) {
    case "issue":
      return { view: "home", issueId: parts[1] };
    case "notice":
      if (parts[1]) return { view: "notice", key: parts[1] };
      break;
    case "letter":
      if ((parts[1] === "notice" || parts[1] === "administration") && parts[2])
        return { view: "letter", scope: parts[1], key: parts[2] };
      break;
    case "chat":
      return { view: "chat", conversationId: parts[1] || undefined };
    case "station":
      if (parts[1]) return { view: "station", id: parts[1] };
      break;
    case "administration":
      if (parts[1]) return { view: "administration", code: parts[1] };
      break;
    case "stats":
      if (parts[1]) return { view: "stats", id: parts[1] };
      break;
    case "notices":
      if ((parts[1] === "issue" || parts[1] === "administration") && parts[2])
        return { view: "notices", scope: parts[1], key: parts[2] };
      break;
    case "cases":
      if (parts[1]) return { view: "cases", key: parts[1] };
      break;
  }
  return { view: "home" };
}

const enc = encodeURIComponent;

export function href(route: Route): string {
  switch (route.view) {
    case "home":
      return route.issueId ? `#/issue/${enc(route.issueId)}` : "#/";
    case "notice":
      return `#/notice/${enc(route.key)}`;
    case "letter":
      return `#/letter/${route.scope}/${enc(route.key)}`;
    case "chat":
      return route.conversationId ? `#/chat/${enc(route.conversationId)}` : "#/chat";
    case "station":
      return `#/station/${enc(route.id)}`;
    case "administration":
      return `#/administration/${enc(route.code)}`;
    case "stats":
      return `#/stats/${enc(route.id)}`;
    case "notices":
      return `#/notices/${route.scope}/${enc(route.key)}`;
    case "cases":
      return `#/cases/${enc(route.key)}`;
  }
}

export function go(route: Route) {
  window.location.hash = href(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      const next = parse(window.location.hash);
      setRoute((prev) => {
        // Switching conversations keeps the scroll position handled by the chat page.
        if (!(prev.view === "chat" && next.view === "chat")) window.scrollTo(0, 0);
        return next;
      });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
