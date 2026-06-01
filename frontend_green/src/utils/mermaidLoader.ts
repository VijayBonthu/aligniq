type MermaidModule = typeof import('mermaid').default;

let mermaidPromise: Promise<MermaidModule> | null = null;

export function loadMermaid(): Promise<MermaidModule> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((m) => {
      const mermaid = m.default;
      // NOTE: keep themeVariables to valid color strings only. A non-color
      // value here (e.g. background: 'transparent') can make mermaid's theme
      // color-math throw during render, which silently drops EVERY diagram to
      // the raw-source fallback. mermaid's dark theme already sits well on the
      // dark diagram container without a background override.
      // htmlLabels:false is REQUIRED for export. With the default htmlLabels,
      // mermaid renders flowchart labels as HTML inside <foreignObject>; drawing
      // such an SVG onto a canvas taints it, so toDataURL/toBlob throws
      // "Tainted canvases may not be exported." (PDF + DOCX). Rendering labels as
      // plain SVG <text> keeps the canvas clean and still renders fine on screen.
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'dark',
        htmlLabels: false,
        flowchart: { htmlLabels: false },
        class: { htmlLabels: false },
        themeVariables: {
          primaryColor: '#1f1411',
          primaryBorderColor: '#3a2a23',
          primaryTextColor: '#f4ece6',
          lineColor: '#7a665b',
        },
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

// Every diagram on a report mounts at once and calls render() simultaneously.
// mermaid.render is NOT concurrency-safe: it mutates global config + a shared
// temporary measurement node it appends to <body>, so parallel calls race and
// the losers throw "Cannot read properties of null (reading 'firstChild')"
// (mermaid's own cleanup touches a node a sibling render already tore down).
// Chain every render through one queue so exactly one runs at a time.
let renderQueue: Promise<unknown> = Promise.resolve();

/**
 * Serialized `mermaid.render`. Returns the SVG string, or throws on failure.
 * Also strips the temporary `d<id>` measurement node mermaid leaves on <body>
 * so it can't accumulate or trip the next render.
 */
export function renderMermaid(id: string, source: string): Promise<string> {
  const run = renderQueue.then(async () => {
    const mermaid = await loadMermaid();
    try {
      const { svg } = await mermaid.render(id, source);
      return svg;
    } finally {
      const orphan = document.getElementById(`d${id}`);
      if (orphan && orphan.parentNode) orphan.parentNode.removeChild(orphan);
    }
  });
  // Swallow rejection on the *queue* copy only (callers still see the real
  // error) so one bad diagram never wedges the renders queued behind it.
  renderQueue = run.catch(() => undefined);
  return run;
}
