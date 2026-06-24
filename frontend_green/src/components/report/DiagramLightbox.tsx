import { useEffect, useRef } from 'react';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { toast } from 'react-hot-toast';
import {
  applyLightThemeToSvgString,
  svgStringToPngBlob,
} from '../../utils/svgExportTheme';

export type LightboxContent =
  | { kind: 'svg'; svg: string; source: string; title?: string }
  | { kind: 'ascii'; source: string; title?: string };

interface Props {
  content: LightboxContent | null;
  onClose: () => void;
}

const LIGHTBOX_RASTER_SCALE = 4;

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function copyImageToClipboard(blob: Blob): Promise<boolean> {
  if (typeof ClipboardItem === 'undefined' || !navigator.clipboard?.write) {
    return false;
  }
  try {
    await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
    return true;
  } catch {
    return false;
  }
}

async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export default function DiagramLightbox({ content, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (content && !dlg.open) dlg.showModal();
    if (!content && dlg.open) dlg.close();
  }, [content]);

  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    const handleClose = () => onClose();
    const handleClick = (e: MouseEvent) => {
      if (e.target === dlg) onClose();
    };
    dlg.addEventListener('close', handleClose);
    dlg.addEventListener('click', handleClick);
    return () => {
      dlg.removeEventListener('close', handleClose);
      dlg.removeEventListener('click', handleClick);
    };
  }, [onClose]);

  if (!content) {
    return <dialog ref={dialogRef} className="diagram-lightbox" />;
  }

  const fileStem = `diagram-${new Date()
    .toISOString()
    .replace(/[:.]/g, '-')
    .slice(0, 19)}`;

  const handleCopy = async () => {
    if (content.kind === 'svg') {
      const png = await svgStringToPngBlob(content.svg, LIGHTBOX_RASTER_SCALE);
      if (png && (await copyImageToClipboard(png.blob))) {
        toast.success('Diagram copied as image');
        return;
      }
      // Fallback: copy the source markdown so user can paste it elsewhere.
      const ok = await copyTextToClipboard(content.source);
      toast[ok ? 'success' : 'error'](
        ok ? 'Image copy not supported — copied source instead' : 'Copy failed',
      );
      return;
    }
    const ok = await copyTextToClipboard(content.source);
    toast[ok ? 'success' : 'error'](ok ? 'Copied to clipboard' : 'Copy failed');
  };

  const handleDownloadPng = async () => {
    if (content.kind !== 'svg') return;
    const png = await svgStringToPngBlob(content.svg, LIGHTBOX_RASTER_SCALE);
    if (!png) {
      toast.error('Could not render diagram');
      return;
    }
    downloadBlob(png.blob, `${fileStem}.png`);
    toast.success('Saved PNG');
  };

  const handleDownloadSvg = async () => {
    if (content.kind !== 'svg') return;
    const themed = applyLightThemeToSvgString(content.svg);
    if (!themed) {
      toast.error('Could not save SVG');
      return;
    }
    downloadBlob(
      new Blob([themed.xml], { type: 'image/svg+xml;charset=utf-8' }),
      `${fileStem}.svg`,
    );
    toast.success('Saved SVG');
  };

  const handleDownloadAscii = () => {
    if (content.kind !== 'ascii') return;
    downloadBlob(
      new Blob([content.source], { type: 'text/plain;charset=utf-8' }),
      `${fileStem}.txt`,
    );
    toast.success('Saved text');
  };

  return (
    <dialog ref={dialogRef} className="diagram-lightbox">
      <div className="diagram-lightbox__bar">
        <span className="diagram-lightbox__title">{content.title || 'Diagram'}</span>
        <div style={{ flex: 1 }} />
        <button type="button" onClick={handleCopy} className="diagram-lightbox__btn">
          Copy
        </button>
        {content.kind === 'svg' ? (
          <>
            <button
              type="button"
              onClick={handleDownloadPng}
              className="diagram-lightbox__btn"
            >
              Download PNG
            </button>
            <button
              type="button"
              onClick={handleDownloadSvg}
              className="diagram-lightbox__btn"
            >
              SVG
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={handleDownloadAscii}
            className="diagram-lightbox__btn"
          >
            Download
          </button>
        )}
        <button
          type="button"
          onClick={onClose}
          className="diagram-lightbox__btn"
          aria-label="Close"
        >
          ✕
        </button>
      </div>
      <div className="diagram-lightbox__stage">
        {content.kind === 'svg' ? (
          <TransformWrapper
            initialScale={1}
            minScale={0.25}
            maxScale={8}
            wheel={{ step: 0.15 }}
            doubleClick={{ step: 0.7 }}
          >
            <TransformComponent
              wrapperStyle={{ width: '100%', height: '100%' }}
              contentStyle={{ width: '100%', height: '100%' }}
            >
              <div
                className="diagram-lightbox__svg"
                dangerouslySetInnerHTML={{ __html: content.svg }}
              />
            </TransformComponent>
          </TransformWrapper>
        ) : (
          <pre className="diagram-lightbox__ascii">{content.source}</pre>
        )}
      </div>
    </dialog>
  );
}
