import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { notifyError } from '../../services/api';
import {
  listVersions,
  setDefaultVersion,
  signoffVersion,
  type ReportVersionMeta,
} from '../../services/chatActionsService';

interface Props {
  chatHistoryId: string;
  open: boolean;
  onClose: () => void;
  /** Called after the active version changes so the host can refresh the report. */
  onChanged?: () => void | Promise<void>;
  /** Seed a scoped comparison question into the chat instead of opening the screen. */
  onAskInChat?: (prompt: string) => void;
}

export default function VersionsPanel({ chatHistoryId, open, onClose, onChanged, onAskInChat }: Props) {
  const navigate = useNavigate();
  const [versions, setVersions] = useState<ReportVersionMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [switchingTo, setSwitchingTo] = useState<number | null>(null);
  const [cmpA, setCmpA] = useState<number | null>(null);
  const [cmpB, setCmpB] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!chatHistoryId) return;
    setLoading(true);
    try {
      const v = await listVersions(chatHistoryId);
      setVersions(v);
      if (v.length >= 2) {
        setCmpA(v[1].version_number);
        setCmpB(v[0].version_number);
      }
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [chatHistoryId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const handleErr = (err: unknown, fallback: string) => notifyError(err, fallback);

  const makeDefault = async (n: number) => {
    setBusy(true);
    setSwitchingTo(n);
    try {
      await setDefaultVersion(chatHistoryId, n);
      await load();
      // Await the host refresh too, so the in-flight indicator persists until the
      // rendered report has actually swapped to this version (not just the API call).
      await onChanged?.();
      toast.success(`v${n} is now the active version`);
    } catch (err) {
      handleErr(err, 'Could not set active version');
    } finally {
      setBusy(false);
      setSwitchingTo(null);
    }
  };

  const pinBaseline = async (n: number) => {
    setBusy(true);
    try {
      await signoffVersion(chatHistoryId, n);
      await load();
      toast.success(`v${n} pinned as the client baseline`);
    } catch (err) {
      handleErr(err, 'Could not pin baseline');
    } finally {
      setBusy(false);
    }
  };

  const goCompare = () => {
    if (cmpA == null || cmpB == null || cmpA === cmpB) {
      toast.error('Pick two different versions');
      return;
    }
    navigate(`/compare/${chatHistoryId}?a=${cmpA}&b=${cmpB}`);
    onClose();
  };

  const askInChat = () => {
    if (cmpA == null || cmpB == null || cmpA === cmpB) {
      toast.error('Pick two different versions');
      return;
    }
    onAskInChat?.(`Compare v${cmpA} and v${cmpB}: what changed in cost, timeline, and architecture?`);
    onClose();
  };

  if (!open) return null;

  return (
    <div style={overlay} onClick={onClose}>
      <div style={drawer} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <span style={titleStyle}>Report versions ({versions.length})</span>
          <button onClick={onClose} style={closeBtn} title="Close">✕</button>
        </div>

        <p style={hint}>Pick which version the chat answers from. The active version also drives exports and search.</p>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px' }}>
          {loading ? (
            <p style={muted}>Loading…</p>
          ) : versions.length === 0 ? (
            <p style={muted}>No versions yet.</p>
          ) : (
            versions.map((v) => {
              // Effective active = the flagged default; if none is flagged (legacy
              // reports), the latest is active — mirrors get_summary_report's fallback.
              const anyDefault = versions.some((x) => x.is_default);
              const active = Boolean(v.is_default) || (!anyDefault && Boolean(v.is_latest));
              const switching = switchingTo === v.version_number;
              // While a switch is in flight, dim the rows that aren't the target so
              // the whole list reads as "locked, working".
              const dimmed = busy && !switching;
              return (
                <div key={v.version_number} style={{ ...rowWrap, opacity: dimmed ? 0.45 : 1 }}>
                  <button
                    onClick={() => !active && !busy && makeDefault(v.version_number)}
                    disabled={busy || active}
                    style={{ ...rowBtn, cursor: busy ? 'progress' : active ? 'default' : 'pointer' }}
                    title={active ? 'Active version' : 'Make this the active version'}
                  >
                    {switching ? (
                      <span style={spinner} aria-label="Switching" />
                    ) : (
                      <span style={{ ...radio, ...(active ? radioOn : {}) }}>
                        {active ? '●' : '○'}
                      </span>
                    )}
                    <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
                      <p style={vTitle}>
                        v{v.version_number}
                        {active && <span style={activeBadge}>ACTIVE</span>}
                        {v.is_client_signoff && <span style={baselineBadge} title={v.signoff_at ? `Signed off ${new Date(v.signoff_at).toLocaleDateString()}` : 'Client baseline'}>★ BASELINE</span>}
                        {v.is_latest && !active && <span style={latestBadge}>latest</span>}
                      </p>
                      <p style={vLabel}>{v.label || v.summary || `Version ${v.version_number}`}</p>
                      {switching ? (
                        <p style={switchingLabel}>Switching…</p>
                      ) : (
                        v.created_at && <p style={ts}>{new Date(v.created_at).toLocaleString()}</p>
                      )}
                    </div>
                  </button>
                  {!v.is_client_signoff && (
                    <button
                      onClick={() => !busy && pinBaseline(v.version_number)}
                      disabled={busy}
                      style={pinBtn}
                      title="Pin as the client-signoff baseline (the change-order baseline)"
                    >
                      Pin baseline
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>

        {versions.length >= 2 && (
          <div style={cmpBox}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <select value={cmpA ?? ''} onChange={(e) => setCmpA(Number(e.target.value))} style={select}>
                {versions.map((v) => <option key={v.version_number} value={v.version_number}>v{v.version_number}</option>)}
              </select>
              <span style={{ color: 'var(--fg-muted)', fontSize: 11 }}>vs</span>
              <select value={cmpB ?? ''} onChange={(e) => setCmpB(Number(e.target.value))} style={select}>
                {versions.map((v) => <option key={v.version_number} value={v.version_number}>v{v.version_number}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button onClick={goCompare} disabled={busy} style={{ ...cmpBtn, flex: 1 }}>Compare ↗</button>
              {onAskInChat && (
                <button onClick={askInChat} disabled={busy} style={{ ...cmpBtn, flex: 1 }}>Ask in chat</button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 60,
  display: 'flex', justifyContent: 'flex-end',
};
const drawer: React.CSSProperties = {
  width: 400, maxWidth: '92vw', height: '100%', background: 'var(--surface)',
  borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
};
const header: React.CSSProperties = {
  height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '0 14px', borderBottom: '1px solid var(--border)',
};
const titleStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-sans)' };
const closeBtn: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 13 };
const hint: React.CSSProperties = { flexShrink: 0, margin: 0, padding: '10px 14px', fontSize: 11, color: 'var(--fg-muted)', lineHeight: 1.4, borderBottom: '1px solid var(--border)' };
const muted: React.CSSProperties = { fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5, padding: '14px 0' };
const rowWrap: React.CSSProperties = {
  display: 'flex', gap: 8, alignItems: 'flex-start', width: '100%',
  borderBottom: '1px solid var(--border)',
};
const rowBtn: React.CSSProperties = {
  display: 'flex', gap: 10, alignItems: 'flex-start', padding: '12px 0', flex: 1, minWidth: 0,
  background: 'none', border: 'none', borderRadius: 0, textAlign: 'left',
};
const pinBtn: React.CSSProperties = {
  flexShrink: 0, alignSelf: 'center', background: 'var(--surface-2)', border: '1px solid var(--border-strong)',
  borderRadius: 8, color: 'var(--fg-dim)', fontSize: 10, padding: '5px 9px', cursor: 'pointer',
  fontFamily: 'var(--font-mono)', letterSpacing: '.03em',
};
const radio: React.CSSProperties = { flexShrink: 0, fontSize: 14, color: 'var(--fg-muted)', lineHeight: '18px' };
const radioOn: React.CSSProperties = { color: 'var(--accent)' };
const spinner: React.CSSProperties = {
  flexShrink: 0, width: 14, height: 14, borderRadius: '50%',
  border: '2px solid var(--border-strong)', borderTopColor: 'var(--accent)',
  animation: 'spin .6s linear infinite', marginTop: 2,
};
const switchingLabel: React.CSSProperties = { margin: '3px 0 0', fontSize: 11, color: 'var(--accent)', fontFamily: 'var(--font-mono)' };
const vTitle: React.CSSProperties = { margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--fg)', display: 'flex', alignItems: 'center', gap: 6 };
const activeBadge: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 8, padding: '2px 5px', borderRadius: 999, background: 'var(--accent-soft)', color: 'var(--accent)', letterSpacing: '.06em' };
const latestBadge: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 8, padding: '2px 5px', borderRadius: 999, background: 'var(--surface-2)', color: 'var(--fg-muted)', letterSpacing: '.06em' };
const baselineBadge: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 8, padding: '2px 5px', borderRadius: 999, background: 'var(--ok-soft)', color: 'var(--ok)', letterSpacing: '.06em' };
const vLabel: React.CSSProperties = { margin: '3px 0 0', fontSize: 12, color: 'var(--fg-dim)', lineHeight: 1.4 };
const ts: React.CSSProperties = { margin: '3px 0 0', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--fg-muted)' };
const cmpBox: React.CSSProperties = { flexShrink: 0, padding: 14, borderTop: '1px solid var(--border)', background: 'var(--surface-2)' };
const select: React.CSSProperties = { flex: 1, minWidth: 0, background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg-dim)', fontSize: 11, fontFamily: 'var(--font-mono)', padding: '6px 8px' };
const cmpBtn: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg)', fontSize: 11, padding: '6px 12px', cursor: 'pointer' };
