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
