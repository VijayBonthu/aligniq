import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import {
  listPendingChanges,
  addPendingChange,
  removePendingChange,
  updatePendingChange,
  clearPendingChanges,
  regenerateReport,
  type PendingChange,
} from '../../services/chatActionsService';

const SECTIONS = ['general', 'tech_stack', 'team_structure', 'timeline', 'risks', 'recommendations', 'executive_summary'];
const CHANGE_TYPES = ['modify', 'add', 'remove', 'replace'];

interface Props {
  chatHistoryId: string;
  open: boolean;
  onClose: () => void;
  /** Optional prefill for the add form (e.g. from "Queue as change" on an analysis). */
  draft?: string;
}

export default function PendingChangesPanel({ chatHistoryId, open, onClose, draft }: Props) {
  const navigate = useNavigate();
  const [changes, setChanges] = useState<PendingChange[]>([]);
  const [hasConflicts, setHasConflicts] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');
  const [section, setSection] = useState('general');
  const [changeType, setChangeType] = useState('modify');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [editSection, setEditSection] = useState('general');
  const [editType, setEditType] = useState('modify');

  const load = useCallback(async () => {
    if (!chatHistoryId) return;
    setLoading(true);
    try {
      const summary = await listPendingChanges(chatHistoryId);
      setChanges(summary.changes);
      setHasConflicts(summary.has_conflicts);
    } catch {
      // non-fatal — panel still usable for adding
    } finally {
      setLoading(false);
    }
  }, [chatHistoryId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  // Prefill the add form when opened with a draft (human edits before queuing).
  useEffect(() => {
    if (open && draft) setText(draft);
  }, [open, draft]);

  const handleErr = (err: unknown, fallback: string) => {
    const detail =
      (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
      (err instanceof Error ? err.message : fallback);
    toast.error(detail);
  };

  const add = async () => {
    const user_request = text.trim();
    if (!user_request) return;
    setBusy(true);
    try {
      await addPendingChange(chatHistoryId, { user_request, target_section: section, change_type: changeType });
      setText('');
      setSection('general');
      setChangeType('modify');
      await load();
      toast.success('Change queued');
    } catch (err) {
      handleErr(err, 'Could not queue change');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    try {
      await removePendingChange(chatHistoryId, id);
      await load();
    } catch (err) {
      handleErr(err, 'Could not remove change');
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (c: PendingChange) => {
    setEditingId(c.id);
    setEditText(c.user_request || '');
    setEditSection(c.target_section || 'general');
    setEditType(c.change_type || 'modify');
  };

  const cancelEdit = () => setEditingId(null);

  const saveEdit = async () => {
    if (!editingId) return;
    const user_request = editText.trim();
    if (!user_request) return;
    setBusy(true);
    try {
      await updatePendingChange(chatHistoryId, editingId, {
        user_request,
        target_section: editSection,
        change_type: editType,
      });
      setEditingId(null);
      await load();
      toast.success('Change updated');
    } catch (err) {
      handleErr(err, 'Could not update change');
    } finally {
      setBusy(false);
    }
  };

  const clearAll = async () => {
    if (!changes.length) return;
    setBusy(true);
    try {
      await clearPendingChanges(chatHistoryId);
      await load();
    } catch (err) {
      handleErr(err, 'Could not clear changes');
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async () => {
    if (!changes.length) return;
    setBusy(true);
    try {
      await regenerateReport(chatHistoryId);
      toast.success('Regenerating with your changes…');
      navigate(`/full-pipeline/${chatHistoryId}`);
    } catch (err) {
      handleErr(err, 'Could not start regeneration');
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div style={overlay} onClick={onClose}>
      <div style={drawer} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <span style={titleStyle}>Pending changes ({changes.length})</span>
          <button onClick={onClose} style={closeBtn} title="Close">✕</button>
        </div>

        {hasConflicts && (
          <div style={conflictBanner}>
            ⚠ Conflicting changes detected — resolve before regenerating.
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
          {loading ? (
            <p style={muted}>Loading…</p>
          ) : changes.length === 0 ? (
            <p style={muted}>No changes queued. Add one below, then regenerate the report.</p>
          ) : (
            changes.map((c) => (
              <div key={c.id} style={changeRow}>
                {editingId === c.id ? (
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={changeId}>{c.id}</p>
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      rows={2}
                      style={{ ...textarea, marginTop: 4 }}
                    />
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <select value={editSection} onChange={(e) => setEditSection(e.target.value)} style={select}>
                        {SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                      <select value={editType} onChange={(e) => setEditType(e.target.value)} style={select}>
                        {CHANGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <button onClick={saveEdit} disabled={busy || !editText.trim()} style={editSaveBtn}>Save</button>
                      <button onClick={cancelEdit} disabled={busy} style={editCancelBtn}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={changeId}>{c.id} · {c.target_section || 'general'}</p>
                      <p style={changeText}>{c.user_request}</p>
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      <button onClick={() => startEdit(c)} disabled={busy} style={rowEdit} title="Edit">✎</button>
                      <button onClick={() => remove(c.id)} disabled={busy} style={rowRemove} title="Remove">✕</button>
                    </div>
                  </>
                )}
              </div>
            ))
          )}
        </div>

        <div style={addBox}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe a change (e.g. Use Redis instead of Postgres for caching)…"
            rows={2}
            style={textarea}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <select value={section} onChange={(e) => setSection(e.target.value)} style={select}>
              {SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={changeType} onChange={(e) => setChangeType(e.target.value)} style={select}>
              {CHANGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <button onClick={add} disabled={busy || !text.trim()} style={addBtn}>Queue</button>
          </div>
        </div>

        <div style={footer}>
          <button onClick={clearAll} disabled={busy || !changes.length} style={clearBtn}>Clear all</button>
          <button onClick={regenerate} disabled={busy || !changes.length} style={regenBtn}>
            Regenerate report →
          </button>
        </div>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 60,
  display: 'flex', justifyContent: 'flex-end',
};
const drawer: React.CSSProperties = {
  width: 380, maxWidth: '90vw', height: '100%', background: 'var(--surface)',
  borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
  animation: 'slideIn .15s ease',
};
const header: React.CSSProperties = {
  height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '0 14px', borderBottom: '1px solid var(--border)',
};
const titleStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-sans)' };
const closeBtn: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 13 };
const muted: React.CSSProperties = { fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5 };
const conflictBanner: React.CSSProperties = {
  padding: '8px 14px', background: 'rgba(52,163,123,.12)', color: 'var(--accent)',
  fontSize: 11, fontFamily: 'var(--font-mono)', borderBottom: '1px solid rgba(52,163,123,.25)',
};
const changeRow: React.CSSProperties = {
  display: 'flex', gap: 8, alignItems: 'flex-start', padding: '10px 0', borderBottom: '1px solid var(--border)',
};
const changeId: React.CSSProperties = { margin: 0, fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--fg-muted)', letterSpacing: '.05em', textTransform: 'uppercase' };
const changeText: React.CSSProperties = { margin: '3px 0 0', fontSize: 12.5, color: 'var(--fg)', lineHeight: 1.4 };
const rowRemove: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 12, flexShrink: 0 };
const rowEdit: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 12, flexShrink: 0 };
const editSaveBtn: React.CSSProperties = {
  background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 6,
  padding: '5px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer',
};
const editCancelBtn: React.CSSProperties = {
  background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 6,
  color: 'var(--fg-dim)', padding: '5px 14px', fontSize: 12, cursor: 'pointer',
};
const addBox: React.CSSProperties = { flexShrink: 0, padding: 14, borderTop: '1px solid var(--border)', background: 'var(--surface-2)' };
const textarea: React.CSSProperties = {
  width: '100%', background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg)', fontSize: 12.5, fontFamily: 'var(--font-sans)', padding: 8, resize: 'vertical', boxSizing: 'border-box',
};
const select: React.CSSProperties = {
  flex: 1, minWidth: 0, background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg-dim)', fontSize: 11, fontFamily: 'var(--font-mono)', padding: '6px 8px',
};
const addBtn: React.CSSProperties = {
  background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8, padding: '6px 14px',
  fontSize: 12, fontWeight: 600, cursor: 'pointer',
};
const footer: React.CSSProperties = {
  flexShrink: 0, display: 'flex', gap: 8, padding: 14, borderTop: '1px solid var(--border)',
};
const clearBtn: React.CSSProperties = {
  flex: 1, background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg-dim)', fontSize: 12, padding: '8px', cursor: 'pointer',
};
const regenBtn: React.CSSProperties = {
  flex: 2, background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8,
  fontSize: 12.5, fontWeight: 600, padding: '8px', cursor: 'pointer',
};
