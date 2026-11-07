// Renders text from the assistant, notifications or anywhere else.
// Supports paragraphs, "- " lists, **bold** and [label](ref) links, and links known
// entity names (satellites, notices, administrations, stations, issues) automatically.
import { Fragment, ReactNode, useMemo } from "react";
import { useData } from "../data";
import { buildEntityIndex, entityMatcher, refHref } from "../links";

type Matcher = ReturnType<typeof entityMatcher>;

let cachedFor: unknown = null;
let cachedMatcher: Matcher = null;

function useMatcher(): Matcher {
  const data = useData();
  return useMemo(() => {
    if (!data) return null;
    if (cachedFor !== data) {
      cachedFor = data;
      cachedMatcher = entityMatcher(buildEntityIndex(data));
    }
    return cachedMatcher;
  }, [data]);
}

export function Ref({ to, children }: { to: string; children: ReactNode }) {
  const h = refHref(to);
  if (!h) return <>{children}</>;
  const external = /^https?:/.test(h);
  return (
    <a
      className="ref"
      href={h}
      target={external ? "_blank" : undefined}
      rel={external ? "noreferrer" : undefined}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </a>
  );
}

function autoLink(text: string, m: Matcher, key: string): ReactNode[] {
  if (!m) return [text];
  const out: ReactNode[] = [];
  let last = 0;
  const re = new RegExp(m.re.source, "g"); // own instance: callers may nest
  for (let hit = re.exec(text); hit; hit = re.exec(text)) {
    if (hit.index > last) out.push(text.slice(last, hit.index));
    out.push(
      <Ref key={`${key}a${hit.index}`} to={m.lookup.get(hit[1])!}>
        {hit[1]}
      </Ref>,
    );
    last = hit.index + hit[1].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const INLINE = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*/.source;

export function inline(text: string, m: Matcher, key = "i", auto = true): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  const re = new RegExp(INLINE, "g"); // own instance: bold text recurses into inline()
  for (let hit = re.exec(text); hit; hit = re.exec(text)) {
    if (hit.index > last) out.push(...(auto ? autoLink(text.slice(last, hit.index), m, `${key}${last}`) : [text.slice(last, hit.index)]));
    if (hit[1] !== undefined) {
      out.push(
        <Ref key={`${key}l${hit.index}`} to={hit[2]}>
          {hit[1]}
        </Ref>,
      );
    } else {
      out.push(<strong key={`${key}b${hit.index}`}>{inline(hit[3], m, `${key}b${hit.index}`, auto)}</strong>);
    }
    last = hit.index + hit[0].length;
  }
  if (last < text.length) out.push(...(auto ? autoLink(text.slice(last), m, `${key}${last}`) : [text.slice(last)]));
  return out;
}

export function RichText({ text, autoLinks = true }: { text: string; autoLinks?: boolean }) {
  const m = useMatcher();
  const blocks = text.split(/\n{2,}/);
  return (
    <div className="rich">
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        const intro = lines.filter((l) => !/^\s*[-*] /.test(l));
        const items = lines.filter((l) => /^\s*[-*] /.test(l));
        return (
          <Fragment key={bi}>
            {intro.length > 0 && <p>{inline(intro.join(" "), m, `p${bi}`, autoLinks)}</p>}
            {items.length > 0 && (
              <ul>
                {items.map((l, li) => (
                  <li key={li}>{inline(l.replace(/^\s*[-*] /, ""), m, `l${bi}${li}`, autoLinks)}</li>
                ))}
              </ul>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}

/** One line of text, no paragraphs. */
export function InlineText({ text }: { text: string }) {
  const m = useMatcher();
  return <>{inline(text, m)}</>;
}
