import { ReactNode, useMemo } from "react";
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
  const re = new RegExp(m.re.source, "g");
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
  const re = new RegExp(INLINE, "g");
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

type Block =
  | { kind: "p"; text: string }
  | { kind: "h"; text: string }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] };

const BULLET = /^\s*[-*] /;
const NUMBERED = /^\s*\d+[.)]\s+/;
const HEADING = /^\s*#{1,4}\s+/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join(" ") });
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) {
      flush();
      continue;
    }
    if (TABLE_ROW.test(line) && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1])) {
      flush();
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      for (; i < lines.length && TABLE_ROW.test(lines[i]); i++) rows.push(cells(lines[i]));
      i--;
      blocks.push({ kind: "table", head, rows });
      continue;
    }
    if (HEADING.test(line)) {
      flush();
      blocks.push({ kind: "h", text: line.replace(HEADING, "") });
      continue;
    }
    const list = BULLET.test(line) ? "ul" : NUMBERED.test(line) ? "ol" : null;
    if (list) {
      flush();
      const item = line.replace(list === "ul" ? BULLET : NUMBERED, "");
      const prev = blocks[blocks.length - 1];
      if (prev && prev.kind === list) prev.items.push(item);
      else blocks.push({ kind: list, items: [item] });
      continue;
    }
    para.push(line.trim());
  }
  flush();
  return blocks;
}

export function RichText({ text, autoLinks = true }: { text: string; autoLinks?: boolean }) {
  const m = useMatcher();
  const blocks = parseBlocks(text);
  return (
    <div className="rich">
      {blocks.map((b, bi) => {
        const k = `b${bi}`;
        switch (b.kind) {
          case "p":
            return <p key={k}>{inline(b.text, m, k, autoLinks)}</p>;
          case "h":
            return <h4 key={k}>{inline(b.text, m, k, autoLinks)}</h4>;
          case "ul":
          case "ol": {
            const List = b.kind;
            return (
              <List key={k}>
                {b.items.map((item, li) => (
                  <li key={li}>{inline(item, m, `${k}l${li}`, autoLinks)}</li>
                ))}
              </List>
            );
          }
          case "table":
            return (
              <div key={k} className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {b.head.map((h, hi) => (
                        <th key={hi}>{inline(h, m, `${k}h${hi}`, autoLinks)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((row, ri) => (
                      <tr key={ri}>
                        {row.map((cell, ci) => (
                          <td key={ci}>{inline(cell, m, `${k}r${ri}c${ci}`, autoLinks)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}

export function InlineText({ text }: { text: string }) {
  const m = useMatcher();
  return <>{inline(text, m)}</>;
}
