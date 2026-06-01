import DOMPurify from 'dompurify';

// One-time hook: force every link in rendered markdown to open in a new tab
// with safe rel attributes. Citations point at external source URLs, so opening
// them in the same tab would blow away the report the user is reading.
let hookInstalled = false;
function ensureLinkHook() {
  if (hookInstalled) return;
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.nodeName === 'A' && (node as Element).getAttribute('href')) {
      (node as Element).setAttribute('target', '_blank');
      (node as Element).setAttribute('rel', 'noopener noreferrer');
    }
  });
  hookInstalled = true;
}

/**
 * Sanitize marked-generated HTML for safe innerHTML injection, then:
 *  - force links to open in a new tab (target/_blank + rel),
 *  - wrap every <table> in a scroll container so wide tables scroll
 *    horizontally instead of overflowing the report column.
 */
export function sanitizeHtml(html: string): string {
  ensureLinkHook();
  const clean = DOMPurify.sanitize(html, { ADD_ATTR: ['target', 'rel'] });
  // Report markdown never nests tables, so a flat string wrap is reliable.
  return clean
    .replace(/<table(\s|>)/g, '<div class="md-table-wrap"><table$1')
    .replace(/<\/table>/g, '</table></div>');
}

// Mermaid diagram types whose first non-empty line starts a valid diagram.
const MERMAID_KEYWORDS = [
  'graph',
  'flowchart',
  'sequenceDiagram',
  'classDiagram',
  'erDiagram',
  'stateDiagram',
  'stateDiagram-v2',
  'gantt',
  'pie',
  'journey',
  'gitGraph',
  'mindmap',
];

function looksLikeMermaid(body: string): boolean {
  const firstLine = body.trim().split('\n', 1)[0]?.trim() ?? '';
  return MERMAID_KEYWORDS.some(
    (kw) => firstLine === kw || firstLine.startsWith(`${kw} `) || firstLine.startsWith(`${kw}\t`),
  );
}

/**
 * Repair the mermaid syntax LLMs most often get wrong so a diagram renders
 * instead of falling back to raw text. Currently:
 *  - Flowchart/graph node & subgraph labels containing characters mermaid won't
 *    accept unquoted (parentheses, slashes, etc.) get wrapped in double quotes,
 *    e.g. `S[Spoke VNet - Data/Processing (Private Endpoints)]` →
 *         `S["Spoke VNet - Data/Processing (Private Endpoints)"]`.
 *  - SequenceDiagram participant/actor `as` aliases get the same treatment.
 *
 * Only call this as a *fallback* after the original source fails to parse — a
 * valid diagram must never be rewritten.
 */
function quoteLabel(label: string): string {
  const t = label.trim();
  if (t.startsWith('"') && t.endsWith('"') && t.length >= 2) return label;
  return `"${t.replace(/"/g, '#quot;')}"`;
}

export function repairMermaid(src: string): string {
  const head = src.trimStart().split('\n', 1)[0]?.trim() ?? '';
  if (/^(graph|flowchart)\b/i.test(head)) {
    // Quote the inside of single-bracket `id[...]` labels (rectangles + subgraph
    // titles) — the shape that carries free-text service names in architecture
    // diagrams. `[^[\]\n]+` keeps each match within one node and skips the
    // doubled-bracket shapes, so we never corrupt `[[ ]]`/`[( )]`.
    let out = src.replace(/([A-Za-z0-9_]+)\[([^[\]\n]+)\]/g, (_m, id: string, label: string) => {
      return `${id}[${quoteLabel(label)}]`;
    });
    // Quote pipe edge-labels that carry characters the edge-label tokenizer
    // rejects unquoted — parentheses/brackets/braces/semicolons — e.g.
    // `A -->|query via model (RLS)| B` -> `A -->|"query via model (RLS)"| B`.
    // Plain labels (and already-quoted ones) are left untouched.
    out = out.replace(/\|([^|\n]+)\|/g, (m: string, label: string) => {
      const t = label.trim();
      if (t.startsWith('"') && t.endsWith('"')) return m;
      return /[()[\]{};]/.test(t) ? `|${quoteLabel(t)}|` : m;
    });
    return out;
  }
  if (/^sequenceDiagram\b/.test(head)) {
    // Flowchart-style participant labels — `participant S["Scheduler, daily…"]`
    // or `participant S[Scheduler]` — are invalid in a sequenceDiagram: the
    // parser expects `participant S` / `participant S as <name>` and rejects the
    // `[` (the real-world "Expecting 'ACTOR', got 'INVALID'" failure). The LLM
    // borrowed flowchart node syntax; rewrite it to a quoted `as` alias so the
    // whole diagram parses instead of dying on the first participant line.
    let out = src.replace(
      /^(\s*(?:participant|actor)\s+)([A-Za-z0-9_]+)\s*\[\s*(.+?)\s*\]\s*$/gim,
      (_m, pre: string, id: string, label: string) => `${pre}${id} as ${quoteLabel(label)}`,
    );
    // The LLM reuses the same bad bracket shape for inline actor references in
    // message / Note / activate lines (`S["Scheduler"] ->> W["Worker"]: hi`), which
    // the parser also rejects. The declarations above already carry the label via
    // `as`, so strip every remaining `id[…]` down to the bare id.
    out = out.replace(/([A-Za-z0-9_]+)\[[^\]\n]*\]/g, (_m, id: string) => id);
    // Quote bare `as` aliases that carry characters mermaid rejects unquoted. The
    // bracket rewrite above already emits a quoted alias, so this is idempotent.
    out = out.replace(
      /^(\s*(?:participant|actor)\s+\S+\s+as\s+)(.+?)\s*$/gim,
      (_m, pre: string, alias: string) => `${pre}${quoteLabel(alias)}`,
    );
    // `;` is a statement separator in mermaid; LLMs use it as punctuation in
    // message text, which truncates the message and breaks the whole diagram.
    // Replace `;` that appears in a message body (after the first `:`) with `,`.
    out = out
      .split('\n')
      .map((line) => {
        const idx = line.indexOf(':');
        return idx === -1 ? line : line.slice(0, idx + 1) + line.slice(idx + 1).replace(/;/g, ',');
      })
      .join('\n');
    return out;
  }
  return src;
}

const FENCE_RE = /```([A-Za-z0-9_-]*)[ \t]*\n([\s\S]*?)```/g;
// Fence languages that frequently carry mermaid-compatible diagram syntax but
// trip the renderer because they aren't tagged `mermaid`.
const DIAGRAM_ALIASES = new Set(['plantuml', 'uml', 'graphviz', 'dot']);

/**
 * LLMs frequently mislabel a diagram fence (```plantuml, ```uml, untagged, or
 * ```text) even when the body is valid mermaid. Relabel those to ```mermaid so
 * the existing MermaidBlock renderer can turn them into real diagrams instead
 * of dumping them as code text. Already-correct fences are left untouched.
 */
export function normalizeDiagramFences(raw: string): string {
  return raw.replace(FENCE_RE, (match, lang: string, body: string) => {
    const lower = (lang || '').toLowerCase();
    if (lower === 'mermaid' || lower === 'ascii') return match;
    if (DIAGRAM_ALIASES.has(lower) || ((lower === '' || lower === 'text') && looksLikeMermaid(body))) {
      return '```mermaid\n' + body + '```';
    }
    return match;
  });
}
