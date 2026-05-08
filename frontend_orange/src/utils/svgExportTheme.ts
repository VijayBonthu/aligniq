/**
 * Light-theme override for Mermaid-rendered SVGs at export time.
 *
 * The on-screen UI uses a dark mermaid theme. When we rasterize a diagram
 * for PDF/DOCX, those dark colors (light text on dark nodes) get baked into
 * the bitmap and become unreadable on a white printed page. Overriding the
 * dark colors via CSS in the live document does not help, because we
 * rasterize the SVG by serializing it and feeding it to an `<img>`, which
 * does not pick up document-level styles.
 *
 * The fix: inject this stylesheet *inside* the cloned SVG before serializing.
 * Per SVG spec, CSS `!important` rules in an internal `<style>` element win
 * over presentation attributes (`fill="..."`) and over non-`!important`
 * inline styles, so this catches every mermaid diagram type.
 */
export const MERMAID_LIGHT_THEME_OVERRIDE = `
text,
.messageText, .labelText, .loopText, .noteText, .classText, .classTitle,
.label, .edgeLabel, .nodeLabel, .titleText, .actor, .actor > tspan {
  fill: #111111 !important;
  color: #111111 !important;
  stroke: none !important;
  font-family: 'Inter Tight', system-ui, sans-serif !important;
  font-size: 12px !important;
  font-weight: 400 !important;
}
foreignObject *, foreignObject div, foreignObject span, foreignObject p {
  color: #111111 !important;
  background: transparent !important;
  font-family: 'Inter Tight', system-ui, sans-serif !important;
}
.edgeLabel rect, .edgeLabel foreignObject {
  background-color: #ffffff !important;
  fill: #ffffff !important;
}

/* Flowchart / generic node shapes */
.node rect, .node polygon, .node circle, .node ellipse, .node path {
  fill: #faf7f2 !important;
  stroke: #555555 !important;
  stroke-width: 1.2px !important;
}
.cluster rect, .cluster polygon {
  fill: #f1ece4 !important;
  stroke: #c8c2b8 !important;
}

/* Edges + arrows */
.edgePath .path, .edgePath path, .flowchart-link,
line, line.messageLine0, line.messageLine1, .relationshipLine,
path.relation, path.transition {
  stroke: #444444 !important;
  fill: none !important;
}
.edgePath marker path, .arrowheadPath, marker path, defs marker path,
marker polygon {
  fill: #444444 !important;
  stroke: #444444 !important;
}

/* Sequence diagrams */
rect.actor, .actor:not(text), g.actor rect {
  fill: #f4ede2 !important;
  stroke: #555555 !important;
}
.actor-line, line.actor-line {
  stroke: #888888 !important;
  stroke-width: 1px !important;
}
.note, rect.note, g.note rect {
  fill: #fff5e6 !important;
  stroke: #c87a3f !important;
}
.noteText, text.noteText { fill: #5a3815 !important; }
.labelBox, rect.labelBox {
  fill: #efe6d6 !important;
  stroke: #555555 !important;
}
.activation0 { fill: #efe6d6 !important; stroke: #888888 !important; }
.activation1 { fill: #e3d6c0 !important; stroke: #888888 !important; }
.activation2 { fill: #d6c5a8 !important; stroke: #888888 !important; }
.loopLine, .loopText, line.loopLine {
  stroke: #888888 !important;
  fill: #111111 !important;
}

/* ER diagrams */
.entityBox, rect.entityBox { fill: #faf7f2 !important; stroke: #555555 !important; }
.attributeBoxOdd, rect.attributeBoxOdd { fill: #ffffff !important; stroke: #c8c2b8 !important; }
.attributeBoxEven, rect.attributeBoxEven { fill: #faf7f2 !important; stroke: #c8c2b8 !important; }
.relationshipLabelBox { fill: #ffffff !important; stroke: #c8c2b8 !important; }

/* Class diagrams */
.classGroup rect, g.classGroup rect { fill: #faf7f2 !important; stroke: #555555 !important; }
.classGroup line, g.classGroup line { stroke: #555555 !important; }
.classLabel-container { fill: #ffffff !important; stroke: #555555 !important; }

/* State diagrams */
.statediagram-state rect, .statediagram-cluster rect,
g.stateGroup rect, g.stateGroup polygon {
  fill: #faf7f2 !important;
  stroke: #555555 !important;
}
.statediagram-state circle, .start-state, .end-state {
  fill: #555555 !important;
  stroke: #555555 !important;
}

/* Gantt */
.task0, .task1, .task2, .task3 { fill: #c87a3f !important; stroke: #b25a1f !important; }
.taskText0, .taskText1, .taskText2, .taskText3, .taskTextOutsideRight,
.taskTextOutsideLeft { fill: #111111 !important; }
.grid line { stroke: #d8d3cb !important; }

/* Pie */
.pieTitleText, .slice { fill: #111111 !important; }
`;

export interface SerializedSvg {
  xml: string;
  width: number;
  height: number;
}

/** Clone the SVG, inject the light-theme override, and serialize for export. */
export function serializeSvgForExport(svg: SVGSVGElement): SerializedSvg | null {
  const rect = svg.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  if (width <= 0 || height <= 0) return null;

  const cloned = svg.cloneNode(true) as SVGSVGElement;
  cloned.setAttribute('width', String(width));
  cloned.setAttribute('height', String(height));
  cloned.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  if (!cloned.getAttribute('xmlns:xlink')) {
    cloned.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
  }

  const styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style');
  styleEl.setAttribute('type', 'text/css');
  styleEl.textContent = MERMAID_LIGHT_THEME_OVERRIDE;
  cloned.insertBefore(styleEl, cloned.firstChild);

  const xml = new XMLSerializer().serializeToString(cloned);
  return { xml, width, height };
}

/** Rasterize a live SVG to a canvas at the given scale, with light theme. */
export async function rasterizeSvgToCanvas(
  svg: SVGSVGElement,
  scale: number,
): Promise<{ canvas: HTMLCanvasElement; width: number; height: number } | null> {
  const ser = serializeSvgForExport(svg);
  if (!ser) return null;
  return renderSerializedToCanvas(ser, scale);
}

async function renderSerializedToCanvas(
  ser: SerializedSvg,
  scale: number,
): Promise<{ canvas: HTMLCanvasElement; width: number; height: number } | null> {
  const blob = new Blob([ser.xml], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error('svg load failed'));
      i.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(ser.width * scale));
    canvas.height = Math.max(1, Math.round(ser.height * scale));
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return { canvas, width: ser.width, height: ser.height };
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Inject the light-theme override into an SVG that we only have as a string
 * (the lightbox keeps the live mermaid output as XML, not as an element).
 * Returns the themed XML plus the SVG's natural pixel size for downstream
 * rasterization. Falls back to viewBox if width/height attributes are absent.
 */
export function applyLightThemeToSvgString(
  svgXml: string,
): SerializedSvg | null {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgXml, 'image/svg+xml');
  const root = doc.documentElement;
  if (!root || root.nodeName.toLowerCase() !== 'svg') return null;
  if (doc.querySelector('parsererror')) return null;

  const widthAttr = parseFloat(root.getAttribute('width') || '');
  const heightAttr = parseFloat(root.getAttribute('height') || '');
  let width = Number.isFinite(widthAttr) && widthAttr > 0 ? widthAttr : 0;
  let height = Number.isFinite(heightAttr) && heightAttr > 0 ? heightAttr : 0;
  if (!width || !height) {
    const vb = (root.getAttribute('viewBox') || '').trim().split(/\s+/);
    if (vb.length === 4) {
      width = parseFloat(vb[2]) || width;
      height = parseFloat(vb[3]) || height;
    }
  }
  if (!width || !height) return null;
  if (!root.getAttribute('width')) root.setAttribute('width', String(width));
  if (!root.getAttribute('height')) root.setAttribute('height', String(height));
  if (!root.getAttribute('xmlns')) root.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

  const styleEl = doc.createElementNS('http://www.w3.org/2000/svg', 'style');
  styleEl.setAttribute('type', 'text/css');
  styleEl.textContent = MERMAID_LIGHT_THEME_OVERRIDE;
  root.insertBefore(styleEl, root.firstChild);

  const xml = new XMLSerializer().serializeToString(root);
  return { xml, width, height };
}

/** Convert a mermaid SVG string to a PNG blob with the light theme baked in. */
export async function svgStringToPngBlob(
  svgXml: string,
  scale = 3,
): Promise<{ blob: Blob; width: number; height: number } | null> {
  const ser = applyLightThemeToSvgString(svgXml);
  if (!ser) return null;
  const result = await renderSerializedToCanvas(ser, scale);
  if (!result) return null;
  const blob = await new Promise<Blob | null>((resolve) => {
    result.canvas.toBlob((b) => resolve(b), 'image/png', 1.0);
  });
  if (!blob) return null;
  return { blob, width: ser.width, height: ser.height };
}
