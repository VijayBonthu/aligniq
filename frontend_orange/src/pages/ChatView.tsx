import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import useStreamingChat from '../hooks/useStreamingChat';
import RichMessage, { type ChatMessage } from '../components/chat/RichMessage';
import IntegrationsSidebar from '../components/chat/IntegrationsSidebar';
import PreMortemPanel from '../components/chat/PreMortemPanel';
import ToolActivity from '../components/chat/ToolActivity';
import PendingChangesPanel from '../components/chat/PendingChangesPanel';
import VersionsPanel from '../components/chat/VersionsPanel';

type TabKey = 'chat' | 'premortem';

interface ChatRecord {
  chat_history_id: string;
  document_id: string | null;
  title: string | null;
  modified_at?: string | null;
  message?: string | unknown;
  message_count?: number;
  analysis_mode?: 'presales' | 'full';
  presales_id?: string | null;
  pipeline_status?: 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
}

interface QuickAction {
  label: string;
  prompt: string;
}

// Persona-grouped quick-actions that map to existing agent tools, so the chat's
// power is discoverable without typing. Clicking sends the prompt; the agent
// picks the right tool.
const QUICK_ACTIONS: { group: string; actions: QuickAction[] }[] = [
  { group: 'PM', actions: [
    { label: 'Client meeting brief', prompt: 'Prepare a client meeting brief for this project.' },
    { label: 'Blockers & open questions', prompt: 'What are the blockers and open questions I should resolve with the client?' },
  ] },
  { group: 'Exec', actions: [
    { label: 'Go / no-go', prompt: 'Give me an executive go/no-go summary with budget, timeline, and the top risks.' },
  ] },
  { group: 'Architect', actions: [
    { label: 'Technical deep-dive', prompt: 'Give me a technical deep-dive: why this architecture, the trade-offs, and the failure modes to watch.' },
    { label: 'Architecture diagram', prompt: 'Show me the architecture diagram.' },
  ] },
  { group: 'Developer', actions: [
    { label: 'Implementation gotchas', prompt: 'What implementation gotchas and risky assumptions should developers know before starting?' },
    { label: 'Tech stack', prompt: 'What is the recommended tech stack?' },
  ] },
  { group: 'Optimize', actions: [
    { label: 'Cut cost', prompt: 'Analyze cost reduction opportunities with their trade-offs.' },
    { label: 'Speed up timeline', prompt: 'Analyze ways to accelerate the timeline with their trade-offs.' },
  ] },
];

// Mirror of the backend briefing-tool -> label map, so the "Queue as change" /
// export affordances show up on a freshly streamed analysis without a reload.
const TOOL_SAVED_LABELS: Record<string, string> = {
  prepare_client_meeting_brief: 'Client Meeting Brief',
  prepare_executive_summary: 'Executive Summary',
  get_technical_deep_dive: 'Technical Deep-Dive',
  get_implementation_gotchas: 'Implementation Gotchas',
  get_project_blind_spots: 'Blind Spots',
  analyze_cost_reduction: 'Cost Analysis',
  analyze_timeline_acceleration: 'Timeline Analysis',
  suggest_optimization: 'Optimization',
};

function nowTs() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function parseStoredMessages(raw: unknown, projectTitle?: string | null): ChatMessage[] {
  let arr: unknown[] = [];
  try {
    if (typeof raw === 'string') arr = JSON.parse(raw);
    else if (Array.isArray(raw)) arr = raw;
  } catch {
    arr = [];
  }
  return arr
    .filter((m): m is { role: string; content: string; type?: string; saved_label?: string } =>
      Boolean(m && typeof m === 'object' && 'role' in m && 'content' in m),
    )
    .map((m, i) => ({
      id: `m-${i}`,
      role: m.role === 'user' ? 'user' : 'assistant',
      content: String(m.content ?? ''),
      ts: undefined,
      selected: true,
      type: typeof m.type === 'string' ? m.type : undefined,
      reportTitle: projectTitle || undefined,
      savedLabel: typeof m.saved_label === 'string' ? m.saved_label : undefined,
    }));
}

export default function ChatView() {
  const navigate = useNavigate();
  const { user, subscription } = useAuth();
  const { chatHistoryId } = useParams<{ chatHistoryId: string }>();
  const { streamChat, cancelStream, isStreaming, currentContent, thinkingMessage, currentTool, toolStatus } =
    useStreamingChat();

  const [record, setRecord] = useState<ChatRecord | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [contextMode, setContextMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabKey>('chat');
  const [pendingOpen, setPendingOpen] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [changeDraft, setChangeDraft] = useState<string | undefined>(undefined);
  const [savedOnly, setSavedOnly] = useState(false);
  // The assistant message currently streaming; diagrams in it render only once
  // it finishes (an unclosed ```mermaid fence can't be rendered mid-stream).
  const [streamingMsgId, setStreamingMsgId] = useState<string | number | null>(null);
  const reportReady = record?.pipeline_status === 'completed' || record?.pipeline_status === 'idle' || record?.pipeline_status == null;
  // Server is the source of truth on hydration; bumped locally on each send so
  // the indicator updates without re-fetching /chat/{id} after every message.
  const [messageCount, setMessageCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const seqRef = useRef(0);
  // Whether the message list is pinned to the bottom (controls auto-follow while
  // streaming). Updated on scroll; starts true so the initial load lands at the end.
  const atBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);

  useEffect(() => {
    if (!chatHistoryId) {
      navigate('/projects', { replace: true });
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await api.get<{ user_details?: ChatRecord }>(`/chat/${chatHistoryId}`);
        const details = res.data?.user_details;
        if (!details) throw new Error('Project not found');

        if (details.pipeline_status === 'running' || details.pipeline_status === 'queued') {
          navigate(`/full-pipeline/${chatHistoryId}`, { replace: true });
          return;
        }

        // Failed / cancelled: /full-pipeline owns the Retry/Resume surface.
        // Bounce there instead of falling into the wizard via analysis_mode.
        if (details.pipeline_status === 'failed' || details.pipeline_status === 'cancelled') {
          navigate(`/full-pipeline/${chatHistoryId}`, { replace: true });
          return;
        }

        if (details.analysis_mode === 'presales') {
          // Project is still in presales — bounce to wizard.
          navigate(`/new-project/${chatHistoryId}`, { replace: true });
          return;
        }

        const parsed = parseStoredMessages(details.message, details.title);
        seqRef.current = parsed.length;
        if (cancelled) return;
        setRecord(details);
        setMessages(parsed);
        setMessageCount(typeof details.message_count === 'number' ? details.message_count : 0);
      } catch (err) {
        if (cancelled) return;
        const detail =
          (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
          (err instanceof Error ? err.message : 'Project not found');
        toast.error(detail);
        navigate('/projects', { replace: true });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chatHistoryId, navigate]);

  // Stick-to-bottom: only auto-scroll while the user is at/near the bottom. If
  // they scroll up to read mid-stream, leave the viewport where they put it.
  useEffect(() => {
    if (atBottomRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming, currentContent]);

  const handleMessagesScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distanceFromBottom < 80; // px threshold
    atBottomRef.current = atBottom;
    setShowJump((prev) => (prev === !atBottom ? prev : !atBottom));
  };

  const jumpToLatest = () => {
    const el = scrollRef.current;
    if (!el) return;
    atBottomRef.current = true;
    setShowJump(false);
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  };

  const selectedCount = useMemo(
    () => messages.filter((m) => m.selected !== false).length,
    [messages],
  );

  const toggleSelect = (id: ChatMessage['id']) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, selected: !(m.selected !== false) } : m)),
    );
  };

  const messageLimit = subscription?.limits?.messages_per_chat ?? null;
  const messagesRemaining =
    messageLimit == null ? null : Math.max(0, messageLimit - messageCount);
  const atCap = messagesRemaining === 0;

  // Re-fetch the persisted chat so the rendered full_report swaps to the active
  // version after the user picks a different default in the Versions panel.
  const reloadChat = async () => {
    if (!chatHistoryId) return;
    try {
      const res = await api.get<{ user_details?: ChatRecord }>(`/chat/${chatHistoryId}`);
      const details = res.data?.user_details;
      if (!details) return;
      const parsed = parseStoredMessages(details.message, details.title);
      seqRef.current = parsed.length;
      setRecord(details);
      setMessages(parsed);
      setMessageCount(typeof details.message_count === 'number' ? details.message_count : 0);
    } catch {
      /* non-fatal */
    }
  };

  const send = async (textOverride?: string) => {
    const trimmed = (textOverride ?? input).trim();
    if (!trimmed || isStreaming) return;
    if (!record || !chatHistoryId || !user) return;
    if (atCap) {
      navigate('/pricing');
      return;
    }

    const userMsg: ChatMessage = {
      id: `u-${++seqRef.current}`,
      role: 'user',
      content: trimmed,
      ts: nowTs(),
      selected: true,
    };
    const assistantId: ChatMessage['id'] = `a-${++seqRef.current}`;
    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      ts: nowTs(),
      selected: true,
    };
    setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);
    // The user just sent — re-pin to the bottom so their message and the incoming
    // answer scroll into view even if they had scrolled up to read.
    atBottomRef.current = true;
    setShowJump(false);
    setStreamingMsgId(assistantId);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    const token = localStorage.getItem('access_token') || localStorage.getItem('regular_token') || '';

    const payload = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
      selected: contextMode ? m.selected !== false : true,
    }));

    try {
      await streamChat({
        chatHistoryId,
        userId: user.id,
        messages: payload,
        documentId: record.document_id || '',
        title: record.title || '',
        token,
        onToken: (_t, accumulated) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: accumulated } : m)),
          );
        },
        onComplete: (content, toolsUsed) => {
          // If a briefing/analysis tool produced this reply, tag it so the saved
          // badge + export + "Queue as change" affordances appear immediately.
          const label = (toolsUsed || [])
            .map((t) => TOOL_SAVED_LABELS[t.tool])
            .find(Boolean);
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content, savedLabel: label } : m)),
          );
          setStreamingMsgId(null); // stream done — let diagrams render
          // Backend increments per user turn; mirror that locally so the indicator
          // and the cap gate both update without an extra round-trip.
          setMessageCount((c) => c + 1);
        },
        onError: (errMsg) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content || `_Error: ${errMsg}_` }
                : m,
            ),
          );
          setStreamingMsgId(null);
          toast.error(errMsg);
        },
      });
    } catch {
      // useStreamingChat already surfaces via onError above.
    }
  };

  // Prefill the composer (and focus) without sending, so a one-click action can
  // be edited before the user hits Enter. Shared by quick-actions and "Ask in chat".
  const prefillComposer = (prompt: string) => {
    setInput(prompt);
    textareaRef.current?.focus();
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 130)}px`;
  };

  if (loading) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            border: '2px solid var(--border-strong)',
            borderTopColor: 'var(--accent)',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }}
        />
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', animation: 'fadeIn .2s ease' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div
          style={{
            flexShrink: 0,
            height: 50,
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '0 18px',
            background: 'var(--surface)',
          }}
        >
          <button
            onClick={() => navigate('/projects')}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--fg-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              fontSize: 13,
              cursor: 'pointer',
              padding: '4px 6px',
              borderRadius: 6,
              fontFamily: 'var(--font-sans)',
            }}
          >
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path d="M15 18l-6-6 6-6" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Projects
          </button>
          <div style={{ width: 1, height: 18, background: 'var(--border)' }} />
          <span
            style={{
              fontSize: 13.5,
              fontWeight: 500,
              color: 'var(--fg)',
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {record?.title || 'Project chat'}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              letterSpacing: '.08em',
              padding: '3px 8px',
              borderRadius: 999,
              background: 'rgba(122,229,130,.12)',
              color: 'var(--ok)',
              border: '1px solid rgba(122,229,130,.3)',
              textTransform: 'uppercase',
            }}
          >
            FULL REPORT
          </span>
          <button
            onClick={() => reportReady && navigate(`/deliverable/${chatHistoryId}`)}
            disabled={!reportReady}
            title={
              reportReady
                ? 'Curate a client-clean deliverable from this report'
                : 'Available after the full pipeline finishes'
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '5px 11px',
              borderRadius: 999,
              border: `1px solid ${reportReady ? 'var(--accent)' : 'var(--border)'}`,
              background: reportReady ? 'var(--accent-soft)' : 'transparent',
              color: reportReady ? 'var(--accent)' : 'var(--fg-muted)',
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              letterSpacing: '.06em',
              cursor: reportReady ? 'pointer' : 'not-allowed',
              opacity: reportReady ? 1 : 0.6,
            }}
          >
            <svg width="11" height="11" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeWidth="2" strokeLinejoin="round" />
              <path d="M14 2v6h6" strokeWidth="2" strokeLinejoin="round" />
            </svg>
            Build Deliverable
          </button>
          <button
            onClick={() => { if (reportReady) { setChangeDraft(undefined); setPendingOpen(true); } }}
            disabled={!reportReady}
            title="Review queued changes and regenerate the report"
            style={headerPill(reportReady)}
          >
            Changes
          </button>
          <button
            onClick={() => { if (reportReady) setVersionsOpen(true); }}
            disabled={!reportReady}
            title="Compare and roll back report versions"
            style={headerPill(reportReady)}
          >
            Versions
          </button>
          <div
            role="tablist"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 2,
              marginRight: 4,
            }}
          >
            <TabButton
              active={tab === 'chat'}
              onClick={() => setTab('chat')}
              label="Chat"
            />
            <TabButton
              active={tab === 'premortem'}
              onClick={() => reportReady && setTab('premortem')}
              label="Pre-Mortem"
              disabled={!reportReady}
              title={
                reportReady
                  ? 'Adversarial buyer-side objections (CFO / CISO / Procurement)'
                  : 'Pre-Mortem becomes available once the full pipeline finishes'
              }
            />
          </div>
          <button
            onClick={() => setContextMode((p) => !p)}
            title="Select messages to include in LLM context"
            disabled={tab !== 'chat'}
            style={{
              display: tab === 'chat' ? 'flex' : 'none',
              alignItems: 'center',
              gap: 5,
              padding: '5px 10px',
              borderRadius: 999,
              border: `1px solid ${contextMode ? 'var(--accent)' : 'var(--border)'}`,
              background: contextMode ? 'var(--accent-soft)' : 'transparent',
              color: contextMode ? 'var(--accent)' : 'var(--fg-muted)',
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              letterSpacing: '.06em',
              cursor: 'pointer',
            }}
          >
            <svg width="11" height="11" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <polyline points="9 11 12 14 22 4" strokeWidth="2" strokeLinecap="round" />
              <path
                d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"
                strokeWidth="2"
              />
            </svg>
            {contextMode ? `${selectedCount}/${messages.length} in context` : 'Context'}
          </button>
        </div>

        {tab === 'premortem' && chatHistoryId ? (
          <PreMortemPanel chatHistoryId={chatHistoryId} />
        ) : (
        <>
        {contextMode && (
          <div
            style={{
              flexShrink: 0,
              padding: '6px 20px',
              background: 'var(--accent-soft)',
              borderBottom: '1px solid rgba(255,138,101,.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'var(--accent)',
                letterSpacing: '.06em',
              }}
            >
              CONTEXT MODE · {selectedCount}/{messages.length} selected
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setMessages((prev) => prev.map((m) => ({ ...m, selected: true })))}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  color: 'var(--accent)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  letterSpacing: '.06em',
                }}
              >
                SELECT ALL
              </button>
              <button
                onClick={() => setMessages((prev) => prev.map((m) => ({ ...m, selected: false })))}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  color: 'var(--fg-muted)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  letterSpacing: '.06em',
                }}
              >
                CLEAR ALL
              </button>
            </div>
          </div>
        )}

        <div ref={scrollRef} onScroll={handleMessagesScroll} style={{ flex: 1, overflowY: 'auto', padding: '20px 0' }}>
          <div style={{ maxWidth: 780, margin: '0 auto', padding: '0 28px' }}>
            {messages.length === 0 && (
              <div
                style={{
                  textAlign: 'center',
                  padding: '40px 20px',
                  color: 'var(--fg-muted)',
                }}
              >
                <p style={{ fontSize: 14, marginBottom: 8 }}>
                  Ask anything about <strong>{record?.title || 'this project'}</strong>.
                </p>
                <p style={{ fontSize: 12 }}>
                  Risks, architecture, timeline, push items to your connected tools.
                </p>
              </div>
            )}
            {savedOnly && (
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-muted)', textAlign: 'center', margin: '0 0 10px', letterSpacing: '.05em' }}>
                SHOWING SAVED OUTPUTS ONLY
              </p>
            )}
            {messages
              .filter((m) => !savedOnly || Boolean(m.savedLabel))
              .map((m) => (
                <RichMessage
                  key={m.id}
                  msg={m}
                  contextMode={contextMode}
                  onToggleSelect={() => toggleSelect(m.id)}
                  onQueueChange={(text) => { setChangeDraft(text); setPendingOpen(true); }}
                  streaming={isStreaming && m.id === streamingMsgId}
                />
              ))}
            {savedOnly && messages.every((m) => !m.savedLabel) && (
              <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--fg-muted)', padding: '20px' }}>
                No saved briefings yet. Use a persona quick-action (e.g. Go / no-go, Cost analysis) to generate one.
              </p>
            )}
            {isStreaming && thinkingMessage && (
              <p
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--fg-muted)',
                  textAlign: 'center',
                  margin: '6px 0',
                }}
              >
                {thinkingMessage}
              </p>
            )}
            <ToolActivity tool={currentTool} status={toolStatus} />
          </div>
          {showJump && (
            <button
              onClick={jumpToLatest}
              title="Scroll to latest"
              style={{
                position: 'sticky', bottom: 12, left: 0, right: 0, margin: '0 auto',
                width: 'fit-content', zIndex: 5, display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 14px', borderRadius: 999,
                border: '1px solid var(--border-strong)', background: 'var(--surface)',
                color: 'var(--fg-dim)', fontSize: 11.5, fontFamily: 'var(--font-sans)',
                cursor: 'pointer', boxShadow: 'var(--shadow-lg)',
              }}
            >
              ↓ Jump to latest
            </button>
          )}
        </div>

        <div
          style={{
            flexShrink: 0,
            padding: '0 20px 8px',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            maxWidth: 920,
            margin: '0 auto',
            width: '100%',
            overflowX: 'auto',
          }}
        >
          {QUICK_ACTIONS.map((g) => (
            <div key={g.group} style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
              <span
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 8.5, letterSpacing: '.08em',
                  textTransform: 'uppercase', color: 'var(--fg-muted)',
                }}
              >
                {g.group}
              </span>
              {g.actions.map((a) => (
                <button
                  key={a.label}
                  onClick={() => prefillComposer(a.prompt)}
                  disabled={isStreaming || atCap || !reportReady}
                  style={{
                    padding: '5px 11px', borderRadius: 999, border: '1px solid var(--border)',
                    background: 'var(--surface)', color: 'var(--fg-dim)', fontSize: 11,
                    fontFamily: 'var(--font-sans)', cursor: 'pointer', whiteSpace: 'nowrap',
                    opacity: isStreaming || atCap || !reportReady ? 0.5 : 1,
                  }}
                >
                  {a.label}
                </button>
              ))}
            </div>
          ))}
          <div style={{ flex: 1, minWidth: 8 }} />
          <button
            onClick={() => setSavedOnly((v) => !v)}
            title="Show only saved briefings/analyses"
            style={{
              flexShrink: 0, padding: '5px 11px', borderRadius: 999,
              border: `1px solid ${savedOnly ? 'var(--accent)' : 'var(--border)'}`,
              background: savedOnly ? 'var(--accent-soft)' : 'var(--surface)',
              color: savedOnly ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 11,
              fontFamily: 'var(--font-mono)', letterSpacing: '.04em', cursor: 'pointer', whiteSpace: 'nowrap',
            }}
          >
            {savedOnly ? '✕ Saved' : '★ Saved'}
          </button>
        </div>

        <div
          style={{
            flexShrink: 0,
            borderTop: '1px solid var(--border)',
            background: 'var(--surface)',
            padding: '10px 18px 14px',
          }}
        >
          <div style={{ maxWidth: 780, margin: '0 auto' }}>
            {messageLimit != null && (
              <div
                style={{
                  marginBottom: 6,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  letterSpacing: '.04em',
                  color: atCap
                    ? 'var(--danger)'
                    : (messagesRemaining ?? messageLimit) <= Math.max(1, Math.floor(messageLimit * 0.2))
                    ? 'var(--warn)'
                    : 'var(--fg-muted)',
                }}
              >
                <span>
                  {atCap
                    ? `Message limit reached for this chat (${messageCount}/${messageLimit})`
                    : `${messageCount} / ${messageLimit} messages used`}
                </span>
                {atCap && (
                  <button
                    type="button"
                    onClick={() => navigate('/pricing')}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--accent)',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      fontSize: 'inherit',
                      letterSpacing: 'inherit',
                      padding: 0,
                    }}
                  >
                    UPGRADE →
                  </button>
                )}
              </div>
            )}
            {contextMode && (
              <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    color: 'var(--fg-muted)',
                    letterSpacing: '.06em',
                  }}
                >
                  SENDING {selectedCount} MESSAGE{selectedCount !== 1 ? 'S' : ''} AS CONTEXT
                </span>
                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              </div>
            )}
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-end',
                gap: 8,
                background: 'var(--surface-2)',
                border: '1px solid var(--border-strong)',
                borderRadius: 11,
                padding: '9px 10px',
              }}
            >
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKey}
                placeholder={atCap ? 'Message limit reached for this chat' : 'Ask anything about this project…'}
                rows={1}
                disabled={isStreaming || atCap}
                style={{
                  flex: 1,
                  background: 'none',
                  border: 'none',
                  outline: 'none',
                  color: 'var(--fg)',
                  fontSize: 13.5,
                  fontFamily: 'var(--font-sans)',
                  resize: 'none',
                  lineHeight: 1.5,
                  minHeight: 22,
                  maxHeight: 130,
                }}
              />
              {isStreaming ? (
                <button
                  onClick={cancelStream}
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    border: '1px solid var(--border-strong)',
                    background: 'var(--surface)',
                    color: 'var(--fg-dim)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  title="Stop"
                >
                  <svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                </button>
              ) : (
                <button
                  onClick={() => (atCap ? navigate('/pricing') : void send())}
                  disabled={!input.trim() && !atCap}
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    border: 'none',
                    background: atCap ? 'var(--surface)' : input.trim() ? 'var(--accent)' : 'var(--surface)',
                    color: atCap ? 'var(--fg-muted)' : input.trim() ? '#1a0a04' : 'var(--fg-muted)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: atCap ? 'pointer' : input.trim() ? 'pointer' : 'default',
                  }}
                >
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M22 2L11 13" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M22 2L15 22 11 13 2 9l20-7z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              )}
            </div>
            <p
              style={{
                textAlign: 'center',
                fontFamily: 'var(--font-mono)',
                fontSize: 8.5,
                color: 'var(--fg-muted)',
                marginTop: 5,
                letterSpacing: '.06em',
              }}
            >
              ENTER TO SEND · SHIFT+ENTER FOR NEW LINE
            </p>
          </div>
        </div>
        </>
        )}
      </div>
      <IntegrationsSidebar chatHistoryId={chatHistoryId} />
      {chatHistoryId && (
        <PendingChangesPanel
          chatHistoryId={chatHistoryId}
          open={pendingOpen}
          onClose={() => { setPendingOpen(false); setChangeDraft(undefined); }}
          draft={changeDraft}
        />
      )}
      {chatHistoryId && (
        <VersionsPanel
          chatHistoryId={chatHistoryId}
          open={versionsOpen}
          onClose={() => setVersionsOpen(false)}
          onChanged={reloadChat}
          onAskInChat={(p) => { setVersionsOpen(false); prefillComposer(p); }}
        />
      )}
    </div>
  );
}

function headerPill(enabled: boolean): React.CSSProperties {
  return {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '5px 11px',
    borderRadius: 999,
    border: `1px solid ${enabled ? 'var(--border-strong)' : 'var(--border)'}`,
    background: 'transparent',
    color: enabled ? 'var(--fg-dim)' : 'var(--fg-muted)',
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '.06em',
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.6,
  };
}

function TabButton({
  active,
  onClick,
  label,
  disabled,
  title,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        background: 'transparent',
        border: 'none',
        padding: '6px 12px',
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '.05em',
        textTransform: 'uppercase',
        color: disabled
          ? 'var(--fg-muted)'
          : active
            ? 'var(--fg)'
            : 'var(--fg-dim)',
        borderBottom: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </button>
  );
}
