import React, { useState } from 'react';

type TabKey = 'risks' | 'questions' | 'architecture' | 'timeline' | 'resources';

interface RiskItem { sev: 'high' | 'med' | 'low'; title: string; body: string; }
interface QuestionItem { title: string; body: string; }
interface ArchItem { area: string; choice: string; note: string; }
interface TimelineItem { phase: string; weeks: string; body: string; }
interface ResourceItem { role: string; allocation: string; note: string; }

const SAMPLE_PROJECTS = [
  {
    name: 'RFP · logistics',
    text: 'We need a B2B logistics platform. Real-time tracking, carrier APIs, customer portal. Launch Q2. Mobile support required. EU + US customers. Existing SAP ERP must integrate.',
  },
  {
    name: 'Brief · fintech',
    text: 'Whitelabel lending app for credit unions. KYC, underwriting engine, loan servicing. SOC 2. Target: 50k MAU year one. Mobile-first. Expected uptime 99.99%.',
  },
  {
    name: 'Notes · healthtech',
    text: 'Patient intake portal. HIPAA. EHR integration (Epic). Appointment scheduling. Telehealth video. 12-week target. Nurse admin console. 5 pilot clinics.',
  },
];

const RISKS: RiskItem[] = [
  { sev: 'high', title: 'Data residency unclear', body: 'EU + US customers mentioned but no region plan. GDPR + CCPA scope undefined.' },
  { sev: 'high', title: 'Mobile scope ambiguous', body: 'Native app, hybrid, or responsive web? Each path is a 4-6 week delta.' },
  { sev: 'med', title: 'SAP integration depth', body: 'Read-only vs bidirectional sync not specified. Affects middleware choice.' },
  { sev: 'med', title: 'Q2 launch vs scope', body: 'Tracking + portal + mobile in 10 weeks is tight. Suggest phasing.' },
  { sev: 'low', title: 'Carrier API list not fixed', body: 'FedEx/UPS/DHL confirmed. Regional carriers TBD — 1-2 week each.' },
];

const QUESTIONS: QuestionItem[] = [
  { title: 'Customer portal scope?', body: 'Self-serve quote + tracking, or full order management? Changes auth + billing integration.' },
  { title: 'Data residency plan?', body: 'Single region (where?) or active-active across EU/US? Affects Chroma + Postgres topology.' },
  { title: 'SAP module depth?', body: 'Which IDocs? Which BAPIs? Read-only subscription or write-back to SAP SD?' },
  { title: 'Mobile strategy?', body: 'React Native, Flutter, or PWA? Confirm app store presence requirement.' },
  { title: 'Tracking latency SLA?', body: 'Sub-second live updates or 5-minute refresh? Implies different infra cost tier.' },
];

const ARCH: ArchItem[] = [
  { area: 'Frontend', choice: 'Next.js 15 + React 19', note: 'Streaming RSC for portal, edge-rendered tracking map.' },
  { area: 'Backend', choice: 'FastAPI + LangGraph', note: 'Agent pipeline matches AlignIQ pattern; async carrier fanout.' },
  { area: 'DB', choice: 'Postgres + Chroma', note: 'Transactional + vector search for shipment docs.' },
  { area: 'Queue', choice: 'SQS + EventBridge', note: 'Carrier webhook ingestion, retry on 5xx.' },
  { area: 'Mobile', choice: 'React Native (pending)', note: 'Awaiting confirmation on app store requirement.' },
];

const TIMELINE: TimelineItem[] = [
  { phase: 'Discovery', weeks: 'W1-2', body: 'SAP mapping sessions, carrier onboarding, region decision.' },
  { phase: 'Foundation', weeks: 'W3-5', body: 'Auth, portal shell, tracking data model, carrier 1 integration.' },
  { phase: 'Build', weeks: 'W6-9', body: 'Remaining carriers, SAP sync, mobile beta, SLA dashboards.' },
  { phase: 'Harden', weeks: 'W10-12', body: 'Pen test, GDPR review, load test 10x target, pilot rollout.' },
];

const RESOURCES: ResourceItem[] = [
  { role: 'Tech Lead', allocation: '1.0 FTE', note: 'Architecture + SAP liaison' },
  { role: 'Backend × 2', allocation: '2.0 FTE', note: 'API + carrier integrations + SAP middleware' },
  { role: 'Frontend × 2', allocation: '2.0 FTE', note: 'Portal + admin console' },
  { role: 'Mobile', allocation: '0.5 FTE', note: 'Ramping W3 pending decision' },
  { role: 'DevOps', allocation: '0.5 FTE', note: 'Multi-region infra, observability' },
  { role: 'QA', allocation: '1.0 FTE', note: 'Automation + pen test prep' },
];

const TABS: { key: TabKey; label: string; count: number }[] = [
  { key: 'risks', label: 'Risks', count: RISKS.length },
  { key: 'questions', label: 'Questions', count: QUESTIONS.length },
  { key: 'architecture', label: 'Architecture', count: ARCH.length },
  { key: 'timeline', label: 'Timeline', count: TIMELINE.length },
  { key: 'resources', label: 'Resources', count: RESOURCES.length },
];

export const Demo: React.FC = () => {
  const [text, setText] = useState(SAMPLE_PROJECTS[0].text);
  const [tab, setTab] = useState<TabKey>('risks');
  const [analyzing, setAnalyzing] = useState(false);
  const [revealCounts, setRevealCounts] = useState<Record<TabKey, number>>({
    risks: RISKS.length, questions: QUESTIONS.length, architecture: ARCH.length,
    timeline: TIMELINE.length, resources: RESOURCES.length,
  });

  const run = () => {
    setAnalyzing(true);
    setRevealCounts({ risks: 0, questions: 0, architecture: 0, timeline: 0, resources: 0 });
    const schedule: { key: TabKey; count: number; at: number }[] = [];
    const keys: TabKey[] = ['risks', 'questions', 'architecture', 'timeline', 'resources'];
    const lists = { risks: RISKS, questions: QUESTIONS, architecture: ARCH, timeline: TIMELINE, resources: RESOURCES };
    keys.forEach((k, idx) => {
      const start = 180 + idx * 120;
      lists[k].forEach((_, i) => {
        schedule.push({ key: k, count: i + 1, at: start + i * 160 });
      });
    });
    schedule.forEach(s => {
      window.setTimeout(() => setRevealCounts(prev => ({ ...prev, [s.key]: s.count })), s.at);
    });
    const total = Math.max(...schedule.map(s => s.at));
    window.setTimeout(() => setAnalyzing(false), total + 200);
  };

  const renderPane = () => {
    if (tab === 'risks') {
      const items = RISKS.slice(0, revealCounts.risks);
      if (!items.length) return <div className="demo-empty">Click <b>Run alignment</b> to see detected risks.</div>;
      return items.map((r, i) => (
        <div key={i} className="demo-row">
          <span className={`demo-sev demo-sev-${r.sev}`}>{r.sev.toUpperCase()}</span>
          <div>
            <div className="demo-row-title">{r.title}</div>
            <div className="demo-row-body">{r.body}</div>
          </div>
        </div>
      ));
    }
    if (tab === 'questions') {
      const items = QUESTIONS.slice(0, revealCounts.questions);
      if (!items.length) return <div className="demo-empty">Questions will populate here.</div>;
      return items.map((q, i) => (
        <div key={i} className="demo-row">
          <span className="demo-sev demo-sev-q">Q</span>
          <div>
            <div className="demo-row-title">{q.title}</div>
            <div className="demo-row-body">{q.body}</div>
          </div>
        </div>
      ));
    }
    if (tab === 'architecture') {
      const items = ARCH.slice(0, revealCounts.architecture);
      if (!items.length) return <div className="demo-empty">Architecture decisions appear here.</div>;
      return items.map((a, i) => (
        <div key={i} className="demo-row">
          <span className="demo-sev demo-sev-q">{a.area.slice(0, 3).toUpperCase()}</span>
          <div>
            <div className="demo-row-title">{a.area} · <span style={{ color: 'var(--accent)' }}>{a.choice}</span></div>
            <div className="demo-row-body">{a.note}</div>
          </div>
        </div>
      ));
    }
    if (tab === 'timeline') {
      const items = TIMELINE.slice(0, revealCounts.timeline);
      if (!items.length) return <div className="demo-empty">Phasing and timeline appear here.</div>;
      return items.map((p, i) => (
        <div key={i} className="demo-row">
          <span className="demo-sev demo-sev-q">{p.weeks}</span>
          <div>
            <div className="demo-row-title">{p.phase}</div>
            <div className="demo-row-body">{p.body}</div>
          </div>
        </div>
      ));
    }
    const items = RESOURCES.slice(0, revealCounts.resources);
    if (!items.length) return <div className="demo-empty">Resource plan appears here.</div>;
    return items.map((r, i) => (
      <div key={i} className="demo-row">
        <span className="demo-sev demo-sev-q">{r.allocation}</span>
        <div>
          <div className="demo-row-title">{r.role}</div>
          <div className="demo-row-body">{r.note}</div>
        </div>
      </div>
    ));
  };

  return (
    <div className="demo">
      <div className="demo-topbar">
        <span>alignIQ / scope</span>
        <span>{analyzing ? 'analyzing…' : 'analysis complete · 0.24s'}</span>
      </div>

      <div className="demo-body">
        <div className="demo-input">
          <textarea
            className="demo-textarea"
            value={text}
            onChange={e => setText(e.target.value)}
            spellCheck={false}
          />
          <div className="demo-samples">
            {SAMPLE_PROJECTS.map(p => (
              <button
                key={p.name}
                type="button"
                className="demo-sample"
                onClick={() => setText(p.text)}
              >
                {p.name}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-primary demo-run"
            onClick={run}
            disabled={analyzing}
          >
            {analyzing ? 'Aligning…' : 'Run alignment →'}
          </button>
        </div>

        <div className="demo-output">
          <div className="demo-tabs">
            {TABS.map(t => (
              <button
                key={t.key}
                type="button"
                className={`demo-tab ${tab === t.key ? 'active' : ''}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
                <span className="demo-tab-count">{revealCounts[t.key]}</span>
              </button>
            ))}
          </div>
          <div className="demo-pane">{renderPane()}</div>
        </div>
      </div>
    </div>
  );
};
