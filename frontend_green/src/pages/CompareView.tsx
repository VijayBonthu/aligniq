import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import MarkdownContent from '../components/chat/MarkdownContent';
import { exportMarkdownToPdf } from '../utils/exportPdf';
import {
  listVersions,
  compareVersions,
  getVersionMetrics,
  getVersionSections,
  setDefaultVersion,
  addPendingChange,
  getChangeOrder,
  type ReportVersionMeta,
  type VersionDiff,
  type VersionMetric,
  type VersionSection,
} from '../services/chatActionsService';

type Mode = 'pairwise' | 'matrix';
type Status = 'better' | 'worse' | 'risk' | 'neutral';

const money = (n?: number | null) => (n == null ? '—' : `$${Math.round(n).toLocaleString()}`);
const weeks = (n?: number | null) => (n == null ? '—' : `${n}wk`);
const norm = (h: string) => h.trim().toLowerCase();
const signed = (n: number) => (n >= 0 ? `+${n}` : `${n}`);

const VERDICT_RANK: Record<string, number> = {
  go: 0, 'go-with-conditions': 1, 'conditional-go': 1, 'no-go': 2,
};

function verdictLabel(v?: string | null) {
  if (!v) return '—';
  return v.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function verdictStatus(from?: string | null, to?: string | null): Status {
  if (!from || !to) return 'neutral';
  const rf = VERDICT_RANK[from.toLowerCase()] ?? 9;
  const rt = VERDICT_RANK[to.toLowerCase()] ?? 9;
  if (rt < rf) return 'better';
  if (rt > rf) return 'worse';
  return 'neutral';
}

const STATUS_STYLE: Record<Status, { color: string; icon: string }> = {
  better: { color: 'var(--ok)', icon: '✓' },
  worse: { color: 'var(--danger)', icon: '✗' },
  risk: { color: 'var(--accent)', icon: '⚠' },
  neutral: { color: 'var(--fg-dim)', icon: '·' },
};

export default function CompareView() {
  const { chatHistoryId } = useParams<{ chatHistoryId: string }>();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [versions, setVersions] = useState<ReportVersionMeta[]>([]);
  const [mode, setMode] = useState<Mode>('pairwise');
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);

  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [pairMetrics, setPairMetrics] = useState<VersionMetric[]>([]);
  const [metrics, setMetrics] = useState<VersionMetric[]>([]);
  const [sectionsA, setSectionsA] = useState<VersionSection[]>([]);
  const [sectionsB, setSectionsB] = useState<VersionSection[]>([]);
  const [selectedHeading, setSelectedHeading] = useState<string | null>(null);
  const [drillOpen, setDrillOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mergeText, setMergeText] = useState('');

  const handleErr = (err: unknown, fallback: string) => {
    const detail =
      (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
      (err instanceof Error ? err.message : fallback);
    toast.error(detail);
  };

  // ---- initial load: version list + seed a/b from query ----
  useEffect(() => {
    if (!chatHistoryId) {
      navigate('/projects', { replace: true });
      return;
    }
    (async () => {
      try {
        const v = await listVersions(chatHistoryId);
        setVersions(v);
        const qa = Number(params.get('a'));
        const qb = Number(params.get('b'));
        const valid = (n: number) => v.some((x) => x.version_number === n);
        if (valid(qa) && valid(qb) && qa !== qb) {
          setA(qa);
          setB(qb);
        } else if (v.length >= 2) {
          setA(v[1].version_number);
          setB(v[0].version_number);
        } else if (v.length === 1) {
          setA(v[0].version_number);
          setB(v[0].version_number);
        }
        if (params.get('mode') === 'matrix') setMode('matrix');
      } catch (err) {
        handleErr(err, 'Could not load versions');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatHistoryId]);

  // ---- pairwise data when a/b change ----
  useEffect(() => {
    if (mode !== 'pairwise' || !chatHistoryId || a == null || b == null || a === b) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [d, m, sa, sb] = await Promise.all([
          compareVersions(chatHistoryId, a, b),
          getVersionMetrics(chatHistoryId, [a, b]),
          getVersionSections(chatHistoryId, a),
          getVersionSections(chatHistoryId, b),
        ]);
        if (cancelled) return;
        setDiff(d);
        setPairMetrics(m);
        setSectionsA(sa);
        setSectionsB(sb);
      } catch (err) {
        if (!cancelled) handleErr(err, 'Could not compare versions');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [mode, chatHistoryId, a, b]);

  // ---- matrix data ----
  useEffect(() => {
    if (mode !== 'matrix' || !chatHistoryId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const m = await getVersionMetrics(chatHistoryId);
        if (!cancelled) setMetrics(m);
      } catch (err) {
        if (!cancelled) handleErr(err, 'Could not load metrics');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [mode, chatHistoryId]);

  // union of section headings, version-B order first
  const headings = useMemo(() => {
    const out: { key: string; label: string; hasDiagram: boolean }[] = [];
    const seen = new Set<string>();
    for (const s of [...sectionsB, ...sectionsA]) {
      const k = norm(s.heading);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({ key: k, label: s.heading, hasDiagram: s.has_diagram });
    }
    return out;
  }, [sectionsA, sectionsB]);

  useEffect(() => {
    if (!headings.length) { setSelectedHeading(null); return; }
    setSelectedHeading((cur) => {
      if (cur && headings.some((h) => h.key === cur)) return cur;
      return (headings.find((h) => h.hasDiagram) || headings[0]).key;
    });
  }, [headings]);

  const aMap = useMemo(() => new Map(sectionsA.map((s) => [norm(s.heading), s])), [sectionsA]);
  const bMap = useMemo(() => new Map(sectionsB.map((s) => [norm(s.heading), s])), [sectionsB]);

  const dd = diff?.decision_delta ?? null;
  const ma = useMemo(() => pairMetrics.find((m) => m.version === a), [pairMetrics, a]);
  const mb = useMemo(() => pairMetrics.find((m) => m.version === b), [pairMetrics, b]);

  // Team status: leaner roster or a new staffing gap = a risk worth flagging.
  const teamStatus: Status = useMemo(() => {
    const newGaps = dd?.staffing?.new_gaps?.length ?? 0;
    const removed = dd?.team?.removed?.length ?? 0;
    if (newGaps > 0 || removed > 0) return 'risk';
    return 'neutral';
  }, [dd]);

  const setPair = (na: number, nb: number) => {
    setA(na); setB(nb);
    const p = new URLSearchParams(params);
    p.set('a', String(na)); p.set('b', String(nb)); p.delete('mode');
    setParams(p, { replace: true });
  };

  const makeActive = useCallback(async (n: number) => {
    if (!chatHistoryId) return;
    setBusy(true);
    try {
      await setDefaultVersion(chatHistoryId, n);
      toast.success(`v${n} is now the active version`);
      setVersions(await listVersions(chatHistoryId));
    } catch (err) {
      handleErr(err, 'Could not set active version');
    } finally {
      setBusy(false);
    }
  }, [chatHistoryId]);

  const queueMerge = async () => {
    if (!chatHistoryId || !mergeText.trim()) return;
    setBusy(true);
    try {
      const srcs = a != null && b != null ? ` (from v${a} and v${b})` : '';
      await addPendingChange(chatHistoryId, {
        user_request: `Unify versions${srcs}: ${mergeText.trim()}`,
        target_section: 'general',
        change_type: 'modify',
      });
      toast.success('Queued. Open Changes in the chat, then Regenerate.');
      setMergeText('');
    } catch (err) {
      handleErr(err, 'Could not queue change');
    } finally {
      setBusy(false);
    }
  };

  const exportPdf = async () => {
    if (a == null || b == null) return;
    const lines: string[] = [`# Version comparison — v${a} vs v${b}`, ''];
    if (dd?.cost) lines.push(`- **Cost:** ${money(dd.cost.a_low)}–${money(dd.cost.a_high)} → ${money(dd.cost.b_low)}–${money(dd.cost.b_high)} (${signed(dd.cost.delta_low)}${dd.cost.pct != null ? `, ${signed(dd.cost.pct)}%` : ''})`);
    if (dd?.timeline) lines.push(`- **Timeline:** ${weeks(dd.timeline.a_low)}–${weeks(dd.timeline.a_high)} → ${weeks(dd.timeline.b_low)}–${weeks(dd.timeline.b_high)} (${signed(dd.timeline.delta_low)}wk)`);
    if (dd?.verdict) lines.push(`- **Verdict:** ${verdictLabel(dd.verdict.from)} → ${verdictLabel(dd.verdict.to)}`);
    for (const sw of dd?.tech_swaps ?? []) lines.push(`- **${sw.layer}:** ${sw.type === 'changed' ? `${sw.from} → ${sw.to}` : sw.type === 'added' ? `+ ${sw.to}` : `− ${sw.from}`}${sw.rationale ? ` — ${sw.rationale}` : ''}`);
    for (const g of dd?.staffing?.new_gaps ?? []) lines.push(`- **New staffing gap:** ${g.needed_role}${g.recommendation ? ` (${g.recommendation})` : ''}`);
    if (selectedHeading) {
      const sa = aMap.get(selectedHeading);
      const sb = bMap.get(selectedHeading);
      lines.push('', `## ${sa?.heading || sb?.heading || ''}`, '', `### v${a}`, '', sa?.raw_markdown || '_not present_', '', `### v${b}`, '', sb?.raw_markdown || '_not present_');
    }
    try {
      await exportMarkdownToPdf(lines.join('\n'), `compare-v${a}-v${b}.pdf`, { title: `Compare v${a} vs v${b}` });
    } catch (err) {
      handleErr(err, 'Export failed');
    }
  };

  // The signed baseline + the active version drive the "since sign-off" preset
  // and the change-order draft (the scope-creep-defense artifact).
  const baselineVersion = useMemo(() => versions.find((v) => v.is_client_signoff)?.version_number ?? null, [versions]);
  const activeVersion = useMemo(() => {
    const def = versions.find((v) => v.is_default);
    if (def) return def.version_number;
    return versions.find((v) => v.is_latest)?.version_number ?? versions[0]?.version_number ?? null;
  }, [versions]);

  const sinceSignoff = () => {
    if (baselineVersion == null || activeVersion == null) return;
    if (baselineVersion === activeVersion) {
      toast('The active version IS the signed baseline — nothing has changed yet.');
      return;
    }
    setPair(baselineVersion, activeVersion);
  };

  const draftChangeOrder = async () => {
    if (!chatHistoryId) return;
    setBusy(true);
    try {
      const co = await getChangeOrder(chatHistoryId, 'pdf');
      if (co.pdf_base64) {
        const bytes = atob(co.pdf_base64);
        const arr = new Uint8Array(bytes.length);
        for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
        const url = URL.createObjectURL(new Blob([arr], { type: 'application/pdf' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = co.filename || 'change-order.pdf';
        link.click();
        URL.revokeObjectURL(url);
      }
      toast.success(`Change order drafted: baseline v${co.baseline_version} → v${co.current_version}`);
    } catch (err) {
      handleErr(err, 'Could not draft change order');
    } finally {
      setBusy(false);
    }
  };

  const cheapest = useMemo(() => {
    const priced = metrics.filter((m) => m.cost_low != null);
    return priced.length ? priced.reduce((p, c) => ((c.cost_low as number) < (p.cost_low as number) ? c : p)).version : null;
  }, [metrics]);
  const fastest = useMemo(() => {
    const timed = metrics.filter((m) => m.timeline_weeks_low != null);
    return timed.length ? timed.reduce((p, c) => ((c.timeline_weeks_low as number) < (p.timeline_weeks_low as number) ? c : p)).version : null;
  }, [metrics]);

  const techChanges = dd?.tech_swaps ?? [];
  const teamAdded = dd?.team?.added ?? [];
  const teamRemoved = dd?.team?.removed ?? [];
  const newGaps = dd?.staffing?.new_gaps ?? [];
  const resolvedGaps = dd?.staffing?.resolved_gaps ?? [];
  const msChanged = dd?.timeline_milestones?.changed ?? [];
  const msAdded = dd?.timeline_milestones?.added ?? [];
  const msRemoved = dd?.timeline_milestones?.removed ?? [];
  const hasStaffing = teamAdded.length || teamRemoved.length || newGaps.length || resolvedGaps.length;
  const hasTimeline = msChanged.length || msAdded.length || msRemoved.length;
  const hasChanges = techChanges.length || hasStaffing || hasTimeline;

  return (
    <div style={page}>
      <div style={topbar}>
        <button onClick={() => navigate(`/chat/${chatHistoryId}`)} style={ghostBtn} title="Back to chat">← Chat</button>
        <span style={title}>Compare report versions</span>
        <div style={{ flex: 1 }} />
        <div style={segmented}>
          <button onClick={() => setMode('pairwise')} style={segBtn(mode === 'pairwise')}>Trade-off</button>
          <button onClick={() => setMode('matrix')} style={segBtn(mode === 'matrix')}>All versions</button>
        </div>
      </div>

      {mode === 'pairwise' ? (
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {/* scope selectors + actions */}
          <div style={scopeRow}>
            <select value={a ?? ''} onChange={(e) => setPair(Number(e.target.value), b ?? Number(e.target.value))} style={select}>
              {versions.map((v) => <option key={v.version_number} value={v.version_number}>v{v.version_number}</option>)}
            </select>
            <span style={{ color: 'var(--fg-muted)', fontSize: 12 }}>▸</span>
            <select value={b ?? ''} onChange={(e) => setPair(a ?? Number(e.target.value), Number(e.target.value))} style={select}>
              {versions.map((v) => <option key={v.version_number} value={v.version_number}>v{v.version_number}</option>)}
            </select>
            <div style={{ flex: 1 }} />
            {baselineVersion != null && (
              <button onClick={sinceSignoff} disabled={busy} style={ghostBtn} title={`Compare the signed baseline (v${baselineVersion}) to the active version`}>Since sign-off</button>
            )}
            {baselineVersion != null && (
              <button onClick={draftChangeOrder} disabled={busy} style={primaryBtn} title="Deterministic change order: signed baseline vs current scope">Draft change order</button>
            )}
            {b != null && <button onClick={() => makeActive(b)} disabled={busy} style={primaryBtn}>Set v{b} active</button>}
            <button onClick={exportPdf} disabled={busy || loading} style={ghostBtn}>Export PDF</button>
          </div>

          {/* TRADE-OFF scorecard */}
          <Section label="Trade-off">
            <ScoreRow
              metric="Cost"
              value={mb?.cost_low != null ? `${money(mb.cost_low)}–${money(mb.cost_high)}` : '—'}
              change={dd?.cost ? `${signed(dd.cost.delta_low)}${dd.cost.pct != null ? ` · ${signed(dd.cost.pct)}%` : ''}` : 'no contract data'}
              status={dd?.cost ? (dd.cost.delta_low < 0 ? 'better' : dd.cost.delta_low > 0 ? 'worse' : 'neutral') : 'neutral'}
            />
            <ScoreRow
              metric="Timeline"
              value={mb?.timeline_weeks_low != null ? `${weeks(mb.timeline_weeks_low)}–${weeks(mb.timeline_weeks_high)}` : '—'}
              change={dd?.timeline ? `${signed(dd.timeline.delta_low)}wk` : 'no contract data'}
              status={dd?.timeline ? (dd.timeline.delta_low < 0 ? 'better' : dd.timeline.delta_low > 0 ? 'worse' : 'neutral') : 'neutral'}
            />
            <ScoreRow
              metric="Verdict"
              value={verdictLabel(mb?.verdict ?? dd?.verdict?.to)}
              change={dd?.verdict ? `was ${verdictLabel(dd.verdict.from)}` : 'unchanged'}
              status={dd?.verdict ? verdictStatus(dd.verdict.from, dd.verdict.to) : 'neutral'}
            />
            <ScoreRow
              metric="Team"
              value={mb?.team_count != null ? `${mb.team_count} role${mb.team_count === 1 ? '' : 's'}${mb.team_fte != null ? ` · ${mb.team_fte} FTE` : ''}` : '—'}
              change={
                newGaps.length ? `${newGaps.length} new staffing gap${newGaps.length === 1 ? '' : 's'}`
                  : teamRemoved.length || teamAdded.length ? `${teamRemoved.length ? `−${teamRemoved.length}` : ''}${teamRemoved.length && teamAdded.length ? ' / ' : ''}${teamAdded.length ? `+${teamAdded.length}` : ''} roles`
                    : 'unchanged'
              }
              status={teamStatus}
            />
          </Section>

          {/* WHAT CHANGED — deltas only */}
          {hasChanges ? (
            <Section label="What changed">
              {techChanges.length > 0 && (
                <div style={changeBlock}>
                  <p style={blockTitle}>Tech</p>
                  {techChanges.map((s, i) => (
                    <div key={i} style={changeItem}>
                      <span style={layerTag}>{s.layer}</span>
                      <span style={{ flex: 1 }}>
                        {s.type === 'changed' ? <><span style={delTxt}>{s.from}</span> → <span style={addTxt}>{s.to}</span></>
                          : s.type === 'added' ? <span style={addTxt}>+ {s.to}</span> : <span style={delTxt}>− {s.from}</span>}
                        {s.rationale && <span style={rationale}> — {s.rationale}</span>}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {!!hasStaffing && (
                <div style={changeBlock}>
                  <p style={blockTitle}>Staffing</p>
                  {teamRemoved.map((t, i) => <div key={`r${i}`} style={changeItem}><span style={delTxt}>− {t.label || t.role}</span></div>)}
                  {teamAdded.map((t, i) => <div key={`a${i}`} style={changeItem}><span style={addTxt}>+ {t.label || t.role}</span></div>)}
                  {newGaps.map((g, i) => (
                    <div key={`g${i}`} style={changeItem}>
                      <span style={{ color: 'var(--accent)' }}>⚠ new gap: {g.needed_role}</span>
                      {g.recommendation && <span style={rationale}> — {g.recommendation}</span>}
                    </div>
                  ))}
                  {resolvedGaps.map((g, i) => <div key={`rg${i}`} style={changeItem}><span style={addTxt}>✓ staffed: {g}</span></div>)}
                </div>
              )}

              {!!hasTimeline && (
                <div style={changeBlock}>
                  <p style={blockTitle}>Timeline</p>
                  {msChanged.map((m, i) => (
                    <div key={`c${i}`} style={changeItem}>
                      <span style={{ flex: 1 }}>{m.name}: {weeks(m.a_low)}–{weeks(m.a_high)} → <strong>{weeks(m.b_low)}–{weeks(m.b_high)}</strong></span>
                    </div>
                  ))}
                  {msAdded.map((n, i) => <div key={`ma${i}`} style={changeItem}><span style={addTxt}>+ {n}</span></div>)}
                  {msRemoved.map((n, i) => <div key={`mr${i}`} style={changeItem}><span style={delTxt}>− {n}</span></div>)}
                </div>
              )}
            </Section>
          ) : (
            !loading && <Section label="What changed"><p style={muted}>No structured decision changes detected between these versions.</p></Section>
          )}

          {/* WHY vB */}
          {!!diff?.changes_applied?.length && (
            <Section label={`Why v${b}`}>
              {diff.changes_applied.slice(0, 8).map((c, i) => (
                <p key={i} style={whyLine}>• {String((c as { user_request?: string }).user_request || (c as { description?: string }).description || 'change')}</p>
              ))}
            </Section>
          )}

          {/* DRILL-IN — stacked full-width, on demand */}
          <div style={{ borderTop: '1px solid var(--border)' }}>
            <button onClick={() => setDrillOpen((o) => !o)} style={drillToggle}>
              {drillOpen ? '▾' : '▸'} Compare full sections & diagrams
            </button>
            {drillOpen && (
              <div style={{ padding: '0 16px 16px' }}>
                <div style={chips}>
                  {headings.map((h) => (
                    <button key={h.key} onClick={() => setSelectedHeading(h.key)} style={chip(h.key === selectedHeading)}>
                      {h.hasDiagram && '◇ '}{h.label}
                    </button>
                  ))}
                  {!headings.length && <p style={muted}>{loading ? 'Loading…' : 'No sections.'}</p>}
                </div>
                {selectedHeading && (
                  <div style={stack}>
                    <div style={stackHead}>v{a}</div>
                    <div className="chat-markdown" style={stackBody}>
                      {aMap.get(selectedHeading) ? <MarkdownContent content={aMap.get(selectedHeading)!.raw_markdown} /> : <p style={muted}>— not present in v{a} —</p>}
                    </div>
                    <div style={{ ...stackHead, marginTop: 14 }}>v{b}</div>
                    <div className="chat-markdown" style={stackBody}>
                      {bMap.get(selectedHeading) ? <MarkdownContent content={bMap.get(selectedHeading)!.raw_markdown} /> : <p style={muted}>— not present in v{b} —</p>}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* QUEUE MERGE */}
          <div style={mergeRow}>
            <input
              value={mergeText}
              onChange={(e) => setMergeText(e.target.value)}
              placeholder={`Merge into a new version — e.g. take v${a}'s datastore but keep v${b}'s timeline`}
              style={mergeInput}
              onKeyDown={(e) => { if (e.key === 'Enter') void queueMerge(); }}
            />
            <button onClick={queueMerge} disabled={busy || !mergeText.trim()} style={primaryBtn}>Queue merge change</button>
          </div>
        </div>
      ) : (
        /* matrix */
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          {loading ? (
            <p style={muted}>Loading…</p>
          ) : (
            <table style={table}>
              <thead>
                <tr>
                  <th style={th}>Version</th>
                  <th style={th}>Cost</th>
                  <th style={th}>Timeline</th>
                  <th style={th}>Verdict</th>
                  <th style={th}>Team</th>
                  <th style={th}>Gaps</th>
                  <th style={th}>Active</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => (
                  <tr key={m.version}>
                    <td style={td}><strong>v{m.version}</strong></td>
                    <td style={td}>
                      {m.cost_low != null ? `${money(m.cost_low)}–${money(m.cost_high)}` : '—'}
                      {m.version === cheapest && <span style={pill}>cheapest</span>}
                    </td>
                    <td style={td}>
                      {m.timeline_weeks_low != null ? `${weeks(m.timeline_weeks_low)}–${weeks(m.timeline_weeks_high)}` : '—'}
                      {m.version === fastest && <span style={pill}>fastest</span>}
                    </td>
                    <td style={td}>{verdictLabel(m.verdict)}</td>
                    <td style={td}>{m.team_count != null ? m.team_count : '—'}</td>
                    <td style={td}>{m.staffing_gap_count != null ? (m.staffing_gap_count ? <span style={{ color: 'var(--accent)' }}>{m.staffing_gap_count} ⚠</span> : '0') : '—'}</td>
                    <td style={td}>{m.is_default ? '●' : ''}</td>
                    <td style={td}>{!m.is_default && <button onClick={() => makeActive(m.version)} disabled={busy} style={ghostBtnSm}>Set active</button>}</td>
                  </tr>
                ))}
                {!metrics.length && <tr><td style={td} colSpan={8}><span style={muted}>No versions.</span></td></tr>}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={sectionWrap}>
      <p style={sectionLabel}>{label}</p>
      {children}
    </div>
  );
}

function ScoreRow({ metric, value, change, status }: { metric: string; value: string; change: string; status: Status }) {
  const s = STATUS_STYLE[status];
  return (
    <div style={scoreRow}>
      <span style={{ ...scoreIcon, color: s.color }}>{s.icon}</span>
      <span style={scoreMetric}>{metric}</span>
      <span style={scoreValue}>{value}</span>
      <span style={{ ...scoreChange, color: s.color }}>{change}</span>
    </div>
  );
}

// ---- styles ----
const page: React.CSSProperties = { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' };
const topbar: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 };
const title: React.CSSProperties = { fontSize: 14, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-sans)' };
const segmented: React.CSSProperties = { display: 'flex', border: '1px solid var(--border-strong)', borderRadius: 8, overflow: 'hidden' };
const segBtn = (on: boolean): React.CSSProperties => ({ padding: '6px 12px', fontSize: 11, fontFamily: 'var(--font-mono)', border: 'none', cursor: 'pointer', background: on ? 'var(--accent-soft)' : 'transparent', color: on ? 'var(--accent)' : 'var(--fg-dim)' });
const scopeRow: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px', borderBottom: '1px solid var(--border)' };
const select: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg)', fontSize: 12, fontFamily: 'var(--font-mono)', padding: '6px 10px' };
const sectionWrap: React.CSSProperties = { padding: '12px 16px', borderBottom: '1px solid var(--border)' };
const sectionLabel: React.CSSProperties = { margin: '0 0 8px', fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--fg-muted)' };
const scoreRow: React.CSSProperties = { display: 'flex', alignItems: 'baseline', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--border)' };
const scoreIcon: React.CSSProperties = { width: 14, flexShrink: 0, fontSize: 13, textAlign: 'center' };
const scoreMetric: React.CSSProperties = { width: 80, flexShrink: 0, fontSize: 12, color: 'var(--fg-muted)' };
const scoreValue: React.CSSProperties = { flex: 1, fontSize: 15, fontWeight: 600, color: 'var(--fg)' };
const scoreChange: React.CSSProperties = { fontSize: 12, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' };
const changeBlock: React.CSSProperties = { marginBottom: 10 };
const blockTitle: React.CSSProperties = { margin: '0 0 4px', fontSize: 11, fontWeight: 600, color: 'var(--fg-dim)' };
const changeItem: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'baseline', padding: '3px 0', fontSize: 12.5, color: 'var(--fg-dim)', lineHeight: 1.45 };
const layerTag: React.CSSProperties = { flexShrink: 0, minWidth: 72, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-muted)', textTransform: 'uppercase', letterSpacing: '.04em' };
const rationale: React.CSSProperties = { color: 'var(--fg-muted)', fontSize: 12 };
const addTxt: React.CSSProperties = { color: 'var(--ok)' };
const delTxt: React.CSSProperties = { color: 'var(--danger)' };
const whyLine: React.CSSProperties = { margin: '0 0 4px', fontSize: 12.5, color: 'var(--fg-dim)', lineHeight: 1.45 };
const drillToggle: React.CSSProperties = { width: '100%', textAlign: 'left', padding: '11px 16px', background: 'none', border: 'none', color: 'var(--fg-dim)', fontSize: 12, fontWeight: 600, cursor: 'pointer' };
const chips: React.CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 };
const chip = (on: boolean): React.CSSProperties => ({ padding: '5px 10px', borderRadius: 999, border: `1px solid ${on ? 'var(--accent)' : 'var(--border-strong)'}`, background: on ? 'var(--accent-soft)' : 'transparent', color: on ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 11, cursor: 'pointer' });
const stack: React.CSSProperties = { border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' };
const stackHead: React.CSSProperties = { padding: '7px 12px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--fg-muted)', background: 'var(--surface-2)', borderBottom: '1px solid var(--border)' };
const stackBody: React.CSSProperties = { padding: '12px 14px' };
const mergeRow: React.CSSProperties = { display: 'flex', gap: 8, padding: '12px 16px' };
const mergeInput: React.CSSProperties = { flex: 1, background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg)', fontSize: 13, padding: '8px 12px' };
const primaryBtn: React.CSSProperties = { background: 'var(--accent-soft)', border: '1px solid var(--accent)', color: 'var(--accent)', borderRadius: 8, fontSize: 12, padding: '7px 14px', cursor: 'pointer', whiteSpace: 'nowrap' };
const ghostBtn: React.CSSProperties = { background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--fg-dim)', borderRadius: 8, fontSize: 12, padding: '6px 12px', cursor: 'pointer' };
const ghostBtnSm: React.CSSProperties = { ...ghostBtn, fontSize: 11, padding: '4px 9px' };
const muted: React.CSSProperties = { fontSize: 12, color: 'var(--fg-muted)' };
const table: React.CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 13 };
const th: React.CSSProperties = { textAlign: 'left', padding: '8px 10px', borderBottom: '1px solid var(--border-strong)', fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--fg-muted)' };
const td: React.CSSProperties = { padding: '10px', borderBottom: '1px solid var(--border)', color: 'var(--fg-dim)' };
const pill: React.CSSProperties = { marginLeft: 7, fontFamily: 'var(--font-mono)', fontSize: 8, padding: '2px 6px', borderRadius: 999, background: 'var(--ok-soft)', color: 'var(--ok)', letterSpacing: '.06em' };
