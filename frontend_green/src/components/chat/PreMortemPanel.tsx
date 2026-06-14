import { useEffect, useRef, useState } from 'react';
import { Sev, Tag } from '../ui/Chips';
import { friendlyError } from '../../services/api';
import {
  addPanelist,
  applyItemAction,
  getDefenseBrief,
  getSources,
  getThread,
  postTurn,
  removePanelist,
  resetThread,
} from '../../services/preMortemService';
import type {
  EvidenceRef,
  Item,
  ItemAction,
  Panelist,
  Sources,
  Thread,
  ThreadStatus,
  Turn,
} from '../../types/preMortem';

const STARTER_MESSAGE = 'Surface objections this report invites.';

const DEFAULT_PANELISTS_FALLBACK: Panelist[] = [
  { id: 'cfo', label: 'Skeptical CFO', kind: 'default' },
  { id: 'ciso', label: 'Paranoid CISO', kind: 'default' },
  { id: 'procurement', label: 'Cost-Conscious Procurement', kind: 'default' },
];

function syntheticEmptyThread(): Thread {
  return {
    report_version_id: '',
    model: '',
    panelists: DEFAULT_PANELISTS_FALLBACK,
    turns: [],
  };
}

const PANELIST_BLURBS: Record<string, string> = {
  cfo: 'Total cost, contingency adequacy, ROI, scope-creep exposure.',
  ciso: 'Data residency, encryption, identity, regulatory scope, blast radius.',
  procurement: 'Pricing assumptions, vendor agreements, terms, exit costs.',
};

type View =
  | { kind: 'loading' }
  | { kind: 'report_not_ready' }
  | { kind: 'error'; message: string }
  | { kind: 'ok'; status: ThreadStatus; thread: Thread };

function sevLabel(s: Item['severity']): 'HIGH' | 'MED' | 'LOW' {
  return s === 'high' ? 'HIGH' : s === 'med' ? 'MED' : 'LOW';
}

function evidenceLabel(e: EvidenceRef): string {
  if (e.type === 'vector') return e.label;
  const prefix =
    e.type === 'risk'
      ? `Risk #${(e.ref_index ?? 0) + 1}`
      : e.type === 'assumption'
        ? `Assumption #${(e.ref_index ?? 0) + 1}`
        : e.type === 'open_question'
          ? `Open Q #${(e.ref_index ?? 0) + 1}`
          : 'Section';
  return `${prefix}: ${e.label}`;
}

function sourceArrayFor(ev: EvidenceRef, sources: Sources | null): unknown[] | null {
  if (!sources) return null;
  if (ev.type === 'risk') return sources.key_risks;
  if (ev.type === 'assumption') return sources.critical_assumptions;
  if (ev.type === 'open_question') return sources.open_questions_for_client;
  return null;
}

function sourceText(item: unknown): string {
  if (item == null) return '';
  if (typeof item === 'string') return item;
  if (typeof item === 'object') {
    const obj = item as Record<string, unknown>;
    for (const k of ['title', 'name', 'summary', 'question', 'risk', 'assumption', 'text', 'description']) {
      const v = obj[k];
      if (typeof v === 'string' && v.trim()) return v;
    }
    try {
      return JSON.stringify(item);
    } catch {
      return String(item);
    }
  }
  return String(item);
}

function resolveEvidence(ev: EvidenceRef, sources: Sources | null): string | null {
  // v2 vector evidence: resolve against the attack-surface vectors (title + quote/detail).
  if (ev.type === 'vector') {
    const v = (sources?.vectors || []).find((x) => x.id === ev.vector_id);
    if (!v) return null;
    return v.quote ? `“${v.quote}” — ${v.detail}` : v.detail;
  }
  if (ev.ref_index == null) return null;
  const arr = sourceArrayFor(ev, sources);
  if (!arr || ev.ref_index < 0 || ev.ref_index >= arr.length) return null;
  return sourceText(arr[ev.ref_index]);
}

function money(n?: number | null): string {
  return n == null ? '—' : `$${Math.round(n).toLocaleString()}`;
}

// friendlyError safely flattens an object `detail` (e.g. a 402 payload) to a string, so the
// returned value is always renderable by toast.error().
function errorMessage(err: unknown, fallback: string): string {
  return friendlyError(err, fallback);
}

export default function PreMortemPanel({ chatHistoryId }: { chatHistoryId: string }) {
  const [view, setView] = useState<View>({ kind: 'loading' });
  const [sources, setSources] = useState<Sources | null>(null);
  const [composerText, setComposerText] = useState('');
  const [busy, setBusy] = useState<null | 'turn' | 'panelist' | 'action' | 'reset' | 'export'>(null);
  const [debrief, setDebrief] = useState(false);
  const [showAddPanelist, setShowAddPanelist] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const [newConcern, setNewConcern] = useState('');
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setView({ kind: 'loading' });
    getThread(chatHistoryId)
      .then(res => {
        if (cancelled) return;
        if (res.status === 'report_not_ready') {
          setView({ kind: 'report_not_ready' });
        } else if (res.thread) {
          setView({ kind: 'ok', status: res.status, thread: res.thread });
        } else {
          // Report is ready but no thread persisted yet — show empty room
          // with the default panelists. The first POST /turn lazy-creates
          // the real thread on the server.
          setView({ kind: 'ok', status: 'empty', thread: syntheticEmptyThread() });
        }
      })
      .catch(err => {
        if (cancelled) return;
        setView({ kind: 'error', message: errorMessage(err, 'Failed to load pre-mortem') });
      });
    getSources(chatHistoryId)
      .then(s => {
        if (!cancelled) setSources(s);
      })
      .catch(() => {
        // sources are best-effort; chip fallback handles missing data
      });
    return () => {
      cancelled = true;
    };
  }, [chatHistoryId]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [view, busy]);

  async function sendTurn(message: string, kind: 'starter' | 'user_question') {
    if (!message.trim() || busy) return;
    setBusy('turn');
    try {
      const res = await postTurn(chatHistoryId, { user_message: message.trim(), kind });
      setView({ kind: 'ok', status: 'ready', thread: res.thread });
      if (kind === 'user_question') setComposerText('');
    } catch (err) {
      setView({ kind: 'error', message: errorMessage(err, 'Turn failed') });
    } finally {
      setBusy(null);
    }
  }

  async function onAddPanelist() {
    if (!newLabel.trim() || busy) return;
    setBusy('panelist');
    try {
      const res = await addPanelist(chatHistoryId, {
        label: newLabel.trim(),
        concern: newConcern.trim() || undefined,
      });
      setView(v =>
        v.kind === 'ok' ? { ...v, thread: res.thread } : { kind: 'ok', status: 'empty', thread: res.thread },
      );
      setNewLabel('');
      setNewConcern('');
      setShowAddPanelist(false);
    } catch (err) {
      setView({ kind: 'error', message: errorMessage(err, 'Add panelist failed') });
    } finally {
      setBusy(null);
    }
  }

  async function onRemovePanelist(panelistId: string) {
    if (busy) return;
    setBusy('panelist');
    try {
      const res = await removePanelist(chatHistoryId, panelistId);
      setView(v => (v.kind === 'ok' ? { ...v, thread: res.thread } : v));
    } catch (err) {
      setView({ kind: 'error', message: errorMessage(err, 'Remove panelist failed') });
    } finally {
      setBusy(null);
    }
  }

  async function onItemAction(
    turnId: string, panelistId: string, item: Item, action: ItemAction,
    extra?: { counter_response?: string; came_up?: boolean | null },
  ) {
    // Loop-closing actions only fire on an open item; triage/edit actions work anytime.
    const loopClosing = action === 'add_to_client_qs' || action === 'track_as_change';
    if (busy || (loopClosing && item.status !== 'open')) return;
    setBusy('action');
    try {
      const res = await applyItemAction(chatHistoryId, {
        turn_id: turnId, panelist_id: panelistId, item_id: item.id, action, ...extra,
      });
      setView(v => (v.kind === 'ok' ? { ...v, thread: res.thread } : v));
    } catch (err) {
      setView({ kind: 'error', message: errorMessage(err, 'Action failed') });
    } finally {
      setBusy(null);
    }
  }

  async function onReset() {
    if (busy) return;
    if (!window.confirm('Reset the pre-mortem thread? Custom panelists and turns will be cleared.')) return;
    setBusy('reset');
    try {
      const res = await resetThread(chatHistoryId);
      setView({ kind: 'ok', status: 'empty', thread: res.thread });
    } catch (err) {
      setView({ kind: 'error', message: errorMessage(err, 'Reset failed') });
    } finally {
      setBusy(null);
    }
  }

  async function onExportBrief() {
    if (busy) return;
    setBusy('export');
    try {
      const res = await getDefenseBrief(chatHistoryId, 'pdf', 'severity');
      if (res.pdf_base64) {
        const bytes = atob(res.pdf_base64);
        const arr = new Uint8Array(bytes.length);
        for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
        const url = URL.createObjectURL(new Blob([arr], { type: 'application/pdf' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = res.filename || 'defense-brief.pdf';
        link.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      setView({ kind: 'error', message: errorMessage(err, 'Could not export the Defense Brief') });
    } finally {
      setBusy(null);
    }
  }

  if (view.kind === 'loading') {
    return <CenterMessage title="Loading…" />;
  }
  if (view.kind === 'report_not_ready') {
    return (
      <CenterMessage
        title="Report not ready yet"
        body="Pre-Mortem becomes available once the full pipeline finishes generating the report."
      />
    );
  }
  if (view.kind === 'error') {
    return (
      <CenterMessage
        title="Pre-Mortem error"
        body={view.message}
        tone="danger"
        action={
          <button
            onClick={() => {
              setView({ kind: 'loading' });
              getThread(chatHistoryId)
                .then(r =>
                  r.status === 'report_not_ready'
                    ? setView({ kind: 'report_not_ready' })
                    : r.thread
                      ? setView({ kind: 'ok', status: r.status, thread: r.thread })
                      : setView({ kind: 'ok', status: 'empty', thread: syntheticEmptyThread() }),
                )
                .catch(e => setView({ kind: 'error', message: errorMessage(e, 'Reload failed') }));
            }}
            style={btnGhost}
          >
            Retry
          </button>
        }
      />
    );
  }

  const { thread } = view;
  const turns = thread.turns;
  const isEmpty = turns.length === 0;

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '20px 32px 8px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' }}>
          <div style={{ maxWidth: 720 }}>
            <div className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 6 }}>
              Pre-Mortem · Adversarial Roundtable
            </div>
            <div style={{ color: 'var(--fg-dim)', fontSize: 13, lineHeight: 1.5 }}>
              Rehearse pushback before the meeting. Ask the panel anything — they answer with grounded
              objections you can promote into client questions or tracked changes.
            </div>
          </div>
          {!isEmpty && (
            <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
              <button onClick={onExportBrief} disabled={!!busy} style={btnGhost} title="Export the Defense Brief (objection → answer → evidence) for the meeting">
                {busy === 'export' ? 'Exporting…' : '↧ Defense Brief'}
              </button>
              <button onClick={() => setDebrief(d => !d)} disabled={!!busy} style={debrief ? btnPrimary : btnGhost} title="Toggle post-call debrief — mark which objections actually came up">
                {debrief ? 'Debrief on' : 'Debrief'}
              </button>
              <button onClick={onReset} disabled={!!busy} style={btnGhost}>
                {busy === 'reset' ? 'Resetting…' : 'Reset'}
              </button>
            </div>
          )}
        </div>
        <PanelistStrip
          panelists={thread.panelists}
          busy={busy === 'panelist'}
          onRemove={onRemovePanelist}
          onAddClick={() => setShowAddPanelist(s => !s)}
          showAddForm={showAddPanelist}
        />
        {showAddPanelist && (
          <AddPanelistForm
            label={newLabel}
            concern={newConcern}
            busy={busy === 'panelist'}
            onLabel={setNewLabel}
            onConcern={setNewConcern}
            onSubmit={onAddPanelist}
            onCancel={() => {
              setShowAddPanelist(false);
              setNewLabel('');
              setNewConcern('');
            }}
          />
        )}
      </div>

      <div
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '24px 32px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 24,
        }}
      >
        {isEmpty ? (
          <EmptyThread
            disabled={!!busy}
            onStart={() => sendTurn(STARTER_MESSAGE, 'starter')}
          />
        ) : (
          turns.map(t => (
            <TurnView
              key={t.id}
              turn={t}
              panelists={thread.panelists}
              busyAction={busy === 'action'}
              onItemAction={onItemAction}
              sources={sources}
              debrief={debrief}
            />
          ))
        )}
        {busy === 'turn' && <DeliberatingSkeleton />}
        <div ref={threadEndRef} />
      </div>

      <Composer
        value={composerText}
        onChange={setComposerText}
        disabled={!!busy}
        onSubmit={() => sendTurn(composerText, 'user_question')}
        placeholderEmpty={isEmpty}
        onStart={() => sendTurn(STARTER_MESSAGE, 'starter')}
      />
    </div>
  );
}

function PanelistStrip({
  panelists,
  busy,
  onRemove,
  onAddClick,
  showAddForm,
}: {
  panelists: Panelist[];
  busy: boolean;
  onRemove: (id: string) => void;
  onAddClick: () => void;
  showAddForm: boolean;
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14, alignItems: 'center' }}>
      {panelists.map(p => (
        <span
          key={p.id}
          title={p.kind === 'custom' ? p.concern || p.label : PANELIST_BLURBS[p.id] || p.label}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 10px',
            borderRadius: 999,
            background: p.kind === 'custom' ? 'var(--accent-soft)' : 'var(--surface-2)',
            border: '1px solid var(--border)',
            color: p.kind === 'custom' ? 'var(--accent)' : 'var(--fg)',
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            letterSpacing: '.03em',
          }}
        >
          {p.label}
          {p.kind === 'custom' && (
            <button
              onClick={() => onRemove(p.id)}
              disabled={busy}
              title="Remove panelist"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--accent)',
                cursor: busy ? 'not-allowed' : 'pointer',
                padding: 0,
                fontSize: 14,
                lineHeight: 1,
                opacity: busy ? 0.5 : 1,
              }}
              aria-label={`Remove panelist ${p.label}`}
            >
              ✕
            </button>
          )}
        </span>
      ))}
      <button
        onClick={onAddClick}
        disabled={busy}
        style={{
          background: 'transparent',
          border: '1px dashed var(--border-strong)',
          color: 'var(--fg-dim)',
          padding: '4px 10px',
          borderRadius: 999,
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          cursor: busy ? 'not-allowed' : 'pointer',
          opacity: busy ? 0.5 : 1,
        }}
      >
        {showAddForm ? '− Cancel' : '+ Add panelist'}
      </button>
    </div>
  );
}

function AddPanelistForm({
  label,
  concern,
  busy,
  onLabel,
  onConcern,
  onSubmit,
  onCancel,
}: {
  label: string;
  concern: string;
  busy: boolean;
  onLabel: (s: string) => void;
  onConcern: (s: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      style={{
        marginTop: 12,
        padding: 12,
        borderRadius: 6,
        border: '1px solid var(--border)',
        background: 'var(--surface)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <input
        autoFocus
        value={label}
        onChange={e => onLabel(e.target.value)}
        placeholder='Panelist label (e.g., "Their CTO — ex-Stripe")'
        maxLength={80}
        style={inputStyle}
      />
      <input
        value={concern}
        onChange={e => onConcern(e.target.value)}
        placeholder="What they care about (optional, e.g., 'Postgres maximalist, will push back on NoSQL')"
        maxLength={400}
        style={inputStyle}
      />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onCancel} disabled={busy} style={btnGhost}>
          Cancel
        </button>
        <button onClick={onSubmit} disabled={busy || !label.trim()} style={btnPrimary}>
          {busy ? 'Adding…' : 'Add panelist'}
        </button>
      </div>
    </div>
  );
}

function EmptyThread({ disabled, onStart }: { disabled: boolean; onStart: () => void }) {
  return (
    <div
      style={{
        margin: 'auto',
        textAlign: 'center',
        maxWidth: 560,
        padding: '40px 20px',
        border: '1px dashed var(--border)',
        borderRadius: 8,
        background: 'var(--surface)',
      }}
    >
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, marginBottom: 8, color: 'var(--fg)' }}>
        Empty room. Three default panelists are seated.
      </div>
      <div style={{ color: 'var(--fg-dim)', fontSize: 13, lineHeight: 1.5, marginBottom: 16 }}>
        Tap the starter to get the panel's opening pushback, or ask any specific question — about
        a vendor choice, a cost line, a compliance angle. Add custom panelists to match the actual
        room you're walking into.
      </div>
      <button onClick={onStart} disabled={disabled} style={btnPrimary}>
        Surface objections this report invites
      </button>
    </div>
  );
}

function DeliberatingSkeleton() {
  return (
    <div
      style={{
        padding: '14px 16px',
        border: '1px dashed var(--border)',
        borderRadius: 8,
        background: 'var(--surface)',
        color: 'var(--fg-dim)',
        fontSize: 13,
        fontStyle: 'italic',
      }}
    >
      Panel deliberating…
    </div>
  );
}

type ItemActionFn = (
  turnId: string, panelistId: string, item: Item, action: ItemAction,
  extra?: { counter_response?: string; came_up?: boolean | null },
) => void;

function TurnView({
  turn,
  panelists,
  busyAction,
  onItemAction,
  sources,
  debrief,
}: {
  turn: Turn;
  panelists: Panelist[];
  busyAction: boolean;
  onItemAction: ItemActionFn;
  sources: Sources | null;
  debrief: boolean;
}) {
  const labelMap = new Map(panelists.map(p => [p.id, p.label]));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div
        style={{
          alignSelf: 'flex-end',
          maxWidth: '70%',
          background: 'var(--accent-soft)',
          color: 'var(--fg)',
          border: '1px solid var(--border)',
          padding: '8px 12px',
          borderRadius: 8,
          fontSize: 13,
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--fg-muted)',
            marginBottom: 4,
            letterSpacing: '.06em',
            textTransform: 'uppercase',
          }}
        >
          You · {new Date(turn.ts).toLocaleString()}
        </div>
        {turn.user_message}
      </div>

      {turn.responses.map(r => (
        <PanelistResponseCard
          key={r.panelist_id}
          turnId={turn.id}
          panelistId={r.panelist_id}
          panelistLabel={labelMap.get(r.panelist_id) || r.panelist_id}
          items={r.items}
          busyAction={busyAction}
          onItemAction={onItemAction}
          sources={sources}
          debrief={debrief}
        />
      ))}
      {turn.dropped_items && turn.dropped_items.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--fg-muted)', fontStyle: 'italic', paddingLeft: 4 }}>
          {turn.dropped_items.length} ungrounded objection{turn.dropped_items.length === 1 ? '' : 's'} discarded (not tied to a real finding).
        </div>
      )}
    </div>
  );
}

function PanelistResponseCard({
  turnId,
  panelistId,
  panelistLabel,
  items,
  busyAction,
  onItemAction,
  sources,
  debrief,
}: {
  turnId: string;
  panelistId: string;
  panelistLabel: string;
  items: Item[];
  busyAction: boolean;
  onItemAction: ItemActionFn;
  sources: Sources | null;
  debrief: boolean;
}) {
  return (
    <section
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '14px 16px',
      }}
    >
      <header style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <Tag>{panelistLabel}</Tag>
        <span style={{ color: 'var(--fg-muted)', fontSize: 11 }}>
          {items.length === 0 ? 'no objections this turn' : `${items.length} point${items.length === 1 ? '' : 's'}`}
        </span>
      </header>
      {items.length === 0 ? (
        <div style={{ color: 'var(--fg-dim)', fontSize: 12, fontStyle: 'italic' }}>
          {panelistLabel} has nothing grounded to push back on for this turn.
        </div>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {items.map((it, idx) => (
            <ItemRow
              key={`${turnId}-${panelistId}-${it.id || 'x'}-${idx}`}
              turnId={turnId}
              panelistId={panelistId}
              item={it}
              busy={busyAction}
              onItemAction={onItemAction}
              sources={sources}
              debrief={debrief}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function ItemRow({
  turnId,
  panelistId,
  item,
  busy,
  onItemAction,
  sources,
  debrief,
}: {
  turnId: string;
  panelistId: string;
  item: Item;
  busy: boolean;
  onItemAction: ItemActionFn;
  sources: Sources | null;
  debrief: boolean;
}) {
  const [showSources, setShowSources] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.counter_response);
  const resolvable = (item.evidence || []).filter(e =>
    e.type === 'vector' ? !!e.vector_id : (e.ref_index != null && e.type !== 'section'),
  );
  const hasResolvable = resolvable.length > 0;
  const q = item.quantified;

  return (
    <li
      style={{
        borderTop: '1px solid var(--border)',
        paddingTop: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <Sev level={sevLabel(item.severity)} />
        <div style={{ color: 'var(--fg)', fontSize: 14, lineHeight: 1.5, fontStyle: 'italic', flex: 1 }}>
          “{item.point}”
        </div>
      </div>
      {q && q.scenario_low_usd != null && (
        <div style={{ paddingLeft: 4 }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)',
            background: 'var(--accent-soft)', border: '1px solid var(--border)',
            borderRadius: 4, padding: '3px 8px',
          }}>
            {q.kind === 'worst_case' ? 'Worst case' : 'If this fires'}: {money(q.scenario_low_usd)}–{money(q.scenario_high_usd)}
            {q.delta_pct != null ? ` (${q.delta_pct >= 0 ? '+' : ''}${Math.round(q.delta_pct)}%)` : ''}
          </span>
        </div>
      )}
      {editing ? (
        <div style={{ paddingLeft: 4, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            style={{ width: '100%', boxSizing: 'border-box', background: 'var(--surface-2)', border: '1px solid var(--border-strong)', borderRadius: 6, color: 'var(--fg)', fontSize: 13, padding: '8px 10px', resize: 'vertical' }}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button disabled={busy || !draft.trim()} style={btnAction}
              onClick={() => { onItemAction(turnId, panelistId, item, 'edit_counter', { counter_response: draft }); setEditing(false); }}>
              Save answer
            </button>
            <button style={btnAction} onClick={() => { setDraft(item.counter_response); setEditing(false); }}>Cancel</button>
          </div>
        </div>
      ) : (
        <div style={{ color: 'var(--fg-dim)', fontSize: 13, lineHeight: 1.55, paddingLeft: 4 }}>
          <span style={{ color: 'var(--accent)', marginRight: 6 }}>↳</span>
          {item.counter_response}
          {item.counter_edited && <span style={{ color: 'var(--fg-muted)', fontSize: 10, marginLeft: 6 }}>✎ edited</span>}
          <button
            onClick={() => { setDraft(item.counter_response); setEditing(true); }}
            title="Edit our answer"
            style={{ background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 11, marginLeft: 8, textDecoration: 'underline' }}
          >
            edit
          </button>
        </div>
      )}
      {item.evidence?.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, paddingLeft: 4, alignItems: 'center' }}>
          {item.evidence.map((e, i) => (
            <EvidenceChip key={i} ev={e} />
          ))}
          {hasResolvable && (
            <button
              onClick={() => setShowSources(s => !s)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--fg-muted)',
                cursor: 'pointer',
                fontSize: 10,
                fontFamily: 'var(--font-mono)',
                letterSpacing: '.04em',
                padding: '2px 4px',
                textDecoration: 'underline',
              }}
            >
              {showSources ? 'Hide sources' : 'View sources'}
            </button>
          )}
        </div>
      )}
      {showSources && hasResolvable && (
        <div
          style={{
            marginLeft: 4,
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '8px 10px',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}
        >
          {resolvable.map((e, i) => {
            const text = resolveEvidence(e, sources);
            return (
              <div key={i} style={{ fontSize: 12, lineHeight: 1.5 }}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    color: 'var(--accent)',
                    marginRight: 6,
                    letterSpacing: '.04em',
                  }}
                >
                  {evidenceLabel(e)}
                </span>
                <span style={{ color: text ? 'var(--fg-dim)' : 'var(--fg-muted)', fontStyle: text ? 'normal' : 'italic' }}>
                  {text || '(source not found in current report)'}
                </span>
              </div>
            );
          })}
        </div>
      )}
      <div style={{ paddingLeft: 4, marginTop: 2, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        {item.status === 'added_to_client_qs' ? (
          <StatusPill text="→ Added to client questions" />
        ) : item.status === 'tracked_as_change' ? (
          <StatusPill text="⚙ Tracked as change" />
        ) : (
          <>
            {item.status === 'defended' ? (
              <>
                <StatusPill text="✓ Defended" />
                <button onClick={() => onItemAction(turnId, panelistId, item, 'reopen')} disabled={busy} style={btnAction}>Reopen</button>
              </>
            ) : (
              <button onClick={() => onItemAction(turnId, panelistId, item, 'mark_defended')} disabled={busy} style={btnAction}>✓ Defended</button>
            )}
            <button onClick={() => onItemAction(turnId, panelistId, item, 'add_to_client_qs')} disabled={busy} style={btnAction}>+ Client question</button>
            <button onClick={() => onItemAction(turnId, panelistId, item, 'track_as_change')} disabled={busy} style={btnAction}>⚙ Track as change</button>
          </>
        )}
        {debrief && (
          <span style={{ display: 'flex', gap: 6, alignItems: 'center', marginLeft: 'auto' }}>
            <span style={{ fontSize: 10, color: 'var(--fg-muted)', fontFamily: 'var(--font-mono)' }}>came up?</span>
            <button onClick={() => onItemAction(turnId, panelistId, item, 'mark_came_up', { came_up: item.came_up === true ? null : true })}
              disabled={busy} style={item.came_up === true ? btnPrimary : btnAction}>yes</button>
            <button onClick={() => onItemAction(turnId, panelistId, item, 'mark_came_up', { came_up: item.came_up === false ? null : false })}
              disabled={busy} style={item.came_up === false ? btnPrimary : btnAction}>no</button>
          </span>
        )}
      </div>
    </li>
  );
}

function StatusPill({ text }: { text: string }) {
  return (
    <span style={{
      display: 'inline-block', fontSize: 11, fontFamily: 'var(--font-mono)',
      color: 'var(--ok)', background: 'var(--ok-soft)', border: '1px solid var(--border)',
      padding: '3px 8px', borderRadius: 4, letterSpacing: '.04em',
    }}>
      {text}
    </span>
  );
}

function EvidenceChip({ ev }: { ev: EvidenceRef }) {
  return (
    <span
      title={evidenceLabel(ev)}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        padding: '2px 8px',
        borderRadius: 3,
        background: 'var(--accent-soft)',
        color: 'var(--accent)',
        border: '1px solid var(--border)',
        letterSpacing: '.04em',
        maxWidth: 280,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      {evidenceLabel(ev)}
    </span>
  );
}

function Composer({
  value,
  onChange,
  disabled,
  onSubmit,
  placeholderEmpty,
  onStart,
}: {
  value: string;
  onChange: (s: string) => void;
  disabled: boolean;
  onSubmit: () => void;
  placeholderEmpty: boolean;
  onStart: () => void;
}) {
  return (
    <div
      style={{
        borderTop: '1px solid var(--border)',
        padding: '14px 32px',
        background: 'var(--surface)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', gap: 8 }}>
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder='Ask the panel — e.g., "What will their CFO push back on if we propose AWS over their existing GCP?"'
          rows={2}
          disabled={disabled}
          style={{
            flex: 1,
            resize: 'vertical',
            background: 'var(--surface-2)',
            color: 'var(--fg)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '8px 10px',
            fontSize: 13,
            fontFamily: 'var(--font-sans)',
          }}
        />
        <button onClick={onSubmit} disabled={disabled || !value.trim()} style={btnPrimary}>
          {disabled ? '…' : 'Send'}
        </button>
      </div>
      {placeholderEmpty && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--fg-muted)', fontFamily: 'var(--font-mono)' }}>
            or:
          </span>
          <button onClick={onStart} disabled={disabled} style={btnGhost}>
            Surface objections this report invites
          </button>
        </div>
      )}
      <div style={{ fontSize: 10, color: 'var(--fg-muted)', fontFamily: 'var(--font-mono)' }}>
        ⌘/Ctrl+Enter to send
      </div>
    </div>
  );
}

function CenterMessage({
  title,
  body,
  tone,
  action,
}: {
  title: string;
  body?: string;
  tone?: 'danger';
  action?: React.ReactNode;
}) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
      <div
        style={{
          textAlign: 'center',
          border: '1px dashed var(--border)',
          borderRadius: 8,
          padding: '36px 28px',
          background: 'var(--surface)',
          color: 'var(--fg-dim)',
          maxWidth: 520,
        }}
      >
        <div
          style={{
            fontSize: 14,
            color: tone === 'danger' ? 'var(--danger)' : 'var(--fg)',
            marginBottom: 8,
            fontFamily: 'var(--font-display)',
          }}
        >
          {title}
        </div>
        {body && <div style={{ fontSize: 13, lineHeight: 1.5 }}>{body}</div>}
        {action && <div style={{ marginTop: 14 }}>{action}</div>}
      </div>
    </div>
  );
}

const btnPrimary: React.CSSProperties = {
  background: 'var(--accent)',
  color: '#1a0d05',
  border: 'none',
  padding: '8px 14px',
  borderRadius: 6,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'var(--font-mono)',
  letterSpacing: '.05em',
  textTransform: 'uppercase',
};

const btnGhost: React.CSSProperties = {
  background: 'transparent',
  color: 'var(--fg)',
  border: '1px solid var(--border-strong)',
  padding: '6px 12px',
  borderRadius: 6,
  fontSize: 12,
  cursor: 'pointer',
  fontFamily: 'var(--font-mono)',
  letterSpacing: '.05em',
  textTransform: 'uppercase',
};

const btnAction: React.CSSProperties = {
  background: 'var(--surface-2)',
  color: 'var(--fg)',
  border: '1px solid var(--border)',
  padding: '4px 10px',
  borderRadius: 4,
  fontSize: 11,
  cursor: 'pointer',
  fontFamily: 'var(--font-mono)',
  letterSpacing: '.03em',
};

const inputStyle: React.CSSProperties = {
  background: 'var(--surface-2)',
  color: 'var(--fg)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 13,
  fontFamily: 'var(--font-sans)',
};
