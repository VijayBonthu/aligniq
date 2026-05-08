type MermaidModule = typeof import('mermaid').default;

let mermaidPromise: Promise<MermaidModule> | null = null;

export function loadMermaid(): Promise<MermaidModule> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((m) => {
      const mermaid = m.default;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'dark',
        themeVariables: {
          background: 'transparent',
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
