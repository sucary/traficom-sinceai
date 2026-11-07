// Development only: warns in the console when the page breaks the design rules.
const INPUTS = new Set(["INPUT", "TEXTAREA", "SELECT", "BUTTON", "OPTION", "OPTGROUP"]);
const FORBIDDEN = [/—/, /\s\|\s/, /\s-\s/, /·/, /–/];

function check() {
  const problems: string[] = [];
  document.querySelectorAll<HTMLElement>("body *").forEach((el) => {
    const cs = getComputedStyle(el);
    if (!INPUTS.has(el.tagName)) {
      const sides = ["Top", "Right", "Bottom", "Left"] as const;
      if (sides.some((s) => parseFloat(cs[`border${s}Width`]) > 0 && cs[`border${s}Style`] !== "none"))
        problems.push(`stroke on <${el.tagName.toLowerCase()} class="${el.className}">`);
    }
    if (el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim())) {
      if (cs.color !== "rgb(0, 0, 0)") problems.push(`text colour ${cs.color} on <${el.tagName.toLowerCase()}>`);
    }
  });
  const text = document.body.innerText;
  FORBIDDEN.forEach((re) => {
    const m = text.match(re);
    if (m) problems.push(`forbidden character near "${text.slice(Math.max(0, m.index! - 20), m.index! + 20)}"`);
  });
  document.querySelectorAll<HTMLTextAreaElement>("textarea").forEach((t) => {
    FORBIDDEN.forEach((re) => re.test(t.value) && problems.push(`forbidden character in letter text`));
  });
  if (problems.length) console.warn("Design rule check\n" + [...new Set(problems)].join("\n"));
}

export function startDevCheck() {
  let timer = 0;
  new MutationObserver(() => {
    clearTimeout(timer);
    timer = window.setTimeout(check, 400);
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  window.setTimeout(check, 400);
}
