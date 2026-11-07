// Entity references: turning "notice:ific3074:124545403" into a route, and finding
// known entity names in plain text so they can be linked automatically.
import type { Assessment } from "./data";
import type { EntityRef } from "./api/types";
import { Route, href } from "./router";

export function refToRoute(ref: EntityRef): Route | null {
  const [kind, ...rest] = ref.split(":");
  switch (kind) {
    case "notice":
      return rest.length >= 2 ? { view: "notice", key: `${rest[0]}:${rest.slice(1).join(":")}` } : null;
    case "administration":
      return rest[0] ? { view: "administration", code: rest[0] } : null;
    case "station":
      return rest[0] ? { view: "station", id: rest[0] } : null;
    case "issue":
      return rest[0] ? { view: "home", issueId: rest[0] } : null;
    case "letter":
      if (rest[0] === "notice" && rest.length >= 3)
        return { view: "letter", scope: "notice", key: `${rest[1]}:${rest.slice(2).join(":")}` };
      if (rest[0] === "administration" && rest[1]) return { view: "letter", scope: "administration", key: rest[1] };
      return null;
    case "chat":
      return { view: "chat", conversationId: rest[0] };
    default:
      return null;
  }
}

export function refHref(ref: EntityRef): string | null {
  if (/^https?:\/\//.test(ref)) return ref;
  const r = refToRoute(ref);
  return r ? href(r) : null;
}

export const noticeRef = (key: string) => `notice:${key}`;
export const adminRef = (code: string) => `administration:${code}`;
export const stationRef = (id: string) => `station:${id}`;

export interface Entity {
  text: string;
  ref: EntityRef;
}

/**
 * Names worth linking automatically: satellite names, notice numbers, administration
 * names and Finnish station numbers. Longest names first so "CHINASAT 26" wins over "CHINASAT".
 */
export function buildEntityIndex(data: Assessment): Entity[] {
  const map = new Map<string, EntityRef>();
  for (const n of data.notices) {
    if (!map.has(n.name)) map.set(n.name, noticeRef(n.key));
    map.set(n.noticeId, noticeRef(n.key));
    if (n.administrationName !== n.administration) map.set(n.administrationName, adminRef(n.administration));
    for (const s of n.stations) if (/^\d{5,}$/.test(s.id)) map.set(s.id, stationRef(s.id));
  }
  for (const i of data.issues) map.set(i.label, `issue:${i.id}`);
  return [...map.entries()]
    .filter(([text]) => text.length >= 3)
    .map(([text, ref]) => ({ text, ref }))
    .sort((a, b) => b.text.length - a.text.length);
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function entityMatcher(index: Entity[]) {
  if (!index.length) return null;
  const lookup = new Map(index.map((e) => [e.text, e.ref]));
  const re = new RegExp(`(?<![\\w.])(${index.map((e) => escape(e.text)).join("|")})(?![\\w])`, "g");
  return { re, lookup };
}
