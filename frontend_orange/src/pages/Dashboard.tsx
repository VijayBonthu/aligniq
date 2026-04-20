import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { isAxiosError } from 'axios';
import { toast } from 'react-hot-toast';
import * as marked from 'marked';
import DOMPurify from 'dompurify';
import { useAuth } from '../context/AuthContext';
import { useStreamingChat } from '../hooks/useStreamingChat';
import api from '../services/api';
import * as conversationService from '../services/conversationService';
import { createCheckoutSession } from '../services/billingService';
import type {
  Conversation, Message, GroupedConversations, ConversationMetadata,
  P1Blocker, KickstartQuestion, ReadinessResult, Assumption,
  Contradiction, VagueAnswer, InvalidatedQuestion,
} from '../types';

const API_URL = import.meta.env.VITE_API_URL;
const USE_STREAMING = import.meta.env.VITE_USE_STREAMING === 'true';

// ── Markdown helper ──────────────────────────────────────────────────────────
const sanitizeMarkdown = (content: string): string => {
  const raw = marked.parse(content);
  return DOMPurify.sanitize(typeof raw === 'string' ? raw : String(raw));
};

const MessageContent = React.memo(({ content }: { content: string }) => {
  const html = useMemo(() => sanitizeMarkdown(content), [content]);
  return <div className="prose" dangerouslySetInnerHTML={{ __html: html }} />;
});
MessageContent.displayName = 'MessageContent';

// ── Tool display names ───────────────────────────────────────────────────────
const TOOL_NAMES: Record<string, string> = {
  search_document: 'Searching document',
  get_pending_changes: 'Loading changes',
  add_pending_change: 'Adding change',
  remove_pending_change: 'Removing change',
  clear_all_pending_changes: 'Clearing changes',
  regenerate_report: 'Regenerating report',
  rollback_report: 'Rolling back',
  get_report_section: 'Reading report',
  compare_report_versions: 'Comparing versions',
};
const toolName = (t: string) => TOOL_NAMES[t] || t.replace(/_/g, ' ');

// ── Streaming message ────────────────────────────────────────────────────────
const StreamingMsg: React.FC<{
  content: string; isStreaming: boolean;
  currentTool?: string | null; toolStatus?: string; thinkingMessage?: string | null;
  toolsUsed?: Array<{ tool: string }>;
}> = ({ content, isStreaming, currentTool, toolStatus, thinkingMessage, toolsUsed = [] }) => {
  const html = useMemo(() => (content ? sanitizeMarkdown(content) : ''), [content]);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {thinkingMessage && !currentTool && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--accent-soft)', border: '1px solid rgba(255,138,101,0.2)', borderRadius: 8, fontSize: 13 }}>
          <div style={{ display: 'flex', gap: 3 }}>
            {[0, 150, 300].map(d => (
              <div key={d} style={{ width: 6, height: 6, background: 'var(--accent)', borderRadius: '50%', animation: `bounce 1s ${d}ms ease-in-out infinite` }} />
            ))}
          </div>
          <span style={{ color: 'var(--accent)' }}>{thinkingMessage}</span>
        </div>
      )}
      {currentTool && toolStatus === 'running' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'rgba(74,222,128,0.07)', border: '1px solid rgba(74,222,128,0.15)', borderRadius: 8, fontSize: 13 }}>
          <div className="animate-spin" style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid var(--ok)', borderTopColor: 'transparent' }} />
          <span style={{ color: 'var(--ok)' }}>{toolName(currentTool)}</span>
        </div>
      )}
      {toolsUsed.length > 0 && !isStreaming && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {toolsUsed.map((t, i) => (
            <span key={i} className="badge" style={{ background: 'rgba(74,222,128,0.08)', color: 'var(--ok)', fontSize: 10 }}>{toolName(t.tool)}</span>
          ))}
        </div>
      )}
      {content && (
        <div style={{ position: 'relative' }}>
          <div className="prose" dangerouslySetInnerHTML={{ __html: html }} />
          {isStreaming && <span style={{ display: 'inline-block', width: 8, height: 18, marginLeft: 2, background: 'var(--accent)', verticalAlign: 'middle', animation: 'blink 1s step-end infinite' }} />}
        </div>
      )}
      {!content && isStreaming && !thinkingMessage && !currentTool && (
        <span style={{ display: 'inline-block', width: 8, height: 18, background: 'var(--accent)', animation: 'blink 1s step-end infinite' }} />
      )}
      <style>{`@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}`}</style>
    </div>
  );
};

// ── Sidebar ──────────────────────────────────────────────────────────────────
const Sidebar: React.FC<{
  expanded: boolean; toggle: () => void; onNewChat: () => void;
  onSelectConversation: (id: string) => void; activeId: string | null;
  grouped: GroupedConversations; logout: () => void; isMobile: boolean;
  onDelete: (id: string) => void;
}> = ({ expanded, toggle, onNewChat, onSelectConversation, activeId, grouped, logout, isMobile, onDelete }) => {
  const groups: [string, ConversationMetadata[]][] = [
    ['Today', grouped.today], ['Yesterday', grouped.yesterday],
    ['Last 7 days', grouped.lastWeek], ['Older', grouped.older],
  ];

  const sidebarWidth = expanded ? 256 : (isMobile ? 0 : 56);

  return (
    <>
      {isMobile && expanded && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 20 }} onClick={toggle} />
      )}
      <aside
        style={{
          position: 'fixed', top: 0, left: 0, bottom: 0, zIndex: 30,
          width: sidebarWidth, overflow: 'hidden',
          background: 'var(--surface)', borderRight: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column',
          transition: 'width 0.25s ease',
        }}
      >
        {expanded ? (
          <>
            {/* header */}
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 800, color: '#1a0a04', flexShrink: 0 }}>A</div>
                <span style={{ fontFamily: '"Fraunces", serif', fontWeight: 600, fontSize: 15, color: 'var(--fg)', whiteSpace: 'nowrap' }}>AlignIQ</span>
              </div>
              <button onClick={toggle} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', padding: 4, borderRadius: 4, lineHeight: 0 }}>
                <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 19l-7-7 7-7" strokeWidth="2" strokeLinecap="round"/></svg>
              </button>
            </div>

            {/* new chat */}
            <div style={{ padding: '12px 12px 4px', flexShrink: 0 }}>
              <button
                onClick={onNewChat}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--accent-soft)', border: '1px solid rgba(255,138,101,0.2)', borderRadius: 8, cursor: 'pointer', color: 'var(--accent)', fontSize: 13, fontWeight: 500 }}
              >
                <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" strokeWidth="2" strokeLinecap="round"/></svg>
                New analysis
              </button>
            </div>

            {/* conversation list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
              {groups.map(([label, items]) => items.length > 0 && (
                <div key={label}>
                  <p className="label-mono" style={{ padding: '8px 16px 4px', fontSize: 9 }}>{label.toUpperCase()}</p>
                  {items.map(conv => (
                    <div
                      key={conv.chat_history_id}
                      onClick={() => onSelectConversation(conv.chat_history_id)}
                      style={{
                        padding: '8px 16px', cursor: 'pointer', fontSize: 13,
                        color: activeId === conv.chat_history_id ? 'var(--fg)' : 'var(--fg-dim)',
                        background: activeId === conv.chat_history_id ? 'var(--surface-2)' : 'transparent',
                        borderLeft: activeId === conv.chat_history_id ? '2px solid var(--accent)' : '2px solid transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                        transition: 'all 0.1s',
                      }}
                      onMouseEnter={e => { if (activeId !== conv.chat_history_id) (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'; }}
                      onMouseLeave={e => { if (activeId !== conv.chat_history_id) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                    >
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                        {conv.title || 'Untitled analysis'}
                      </span>
                      <button
                        onClick={e => { e.stopPropagation(); if (confirm('Delete this conversation?')) onDelete(conv.chat_history_id); }}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', padding: 2, lineHeight: 0, flexShrink: 0, opacity: 0, transition: 'opacity 0.15s' }}
                        onMouseEnter={e => (e.currentTarget as HTMLElement).style.opacity = '1'}
                        onMouseLeave={e => (e.currentTarget as HTMLElement).style.opacity = '0'}
                      >
                        <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" strokeWidth="2" strokeLinecap="round"/></svg>
                      </button>
                    </div>
                  ))}
                </div>
              ))}
              {Object.values(grouped).every(g => g.length === 0) && (
                <p style={{ padding: '16px', fontSize: 12, color: 'var(--fg-muted)', textAlign: 'center' }}>No conversations yet</p>
              )}
            </div>

            {/* footer */}
            <div style={{ flexShrink: 0, borderTop: '1px solid var(--border)', padding: 12 }}>
              <button
                onClick={logout}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', fontSize: 13, borderRadius: 6, transition: 'color 0.15s' }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.color = 'var(--fg)'}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.color = 'var(--fg-muted)'}
              >
                <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" strokeWidth="2" strokeLinecap="round"/></svg>
                Sign out
              </button>
            </div>
          </>
        ) : !isMobile ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '12px 0' }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 800, color: '#1a0a04' }}>A</div>
            <button onClick={toggle} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', padding: 6, borderRadius: 4, lineHeight: 0 }}>
              <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7" strokeWidth="2" strokeLinecap="round"/></svg>
            </button>
            <button onClick={onNewChat} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', padding: 6, borderRadius: 4, lineHeight: 0 }}>
              <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" strokeWidth="2" strokeLinecap="round"/></svg>
            </button>
          </div>
        ) : null}

        {/* mobile toggle */}
        {isMobile && !expanded && (
          <button
            onClick={toggle}
            style={{ position: 'fixed', top: 12, left: 12, zIndex: 40, padding: 8, borderRadius: '50%', background: 'var(--surface)', border: '1px solid var(--border-strong)', cursor: 'pointer', lineHeight: 0, boxShadow: '0 2px 8px rgba(0,0,0,0.3)' }}
          >
            <svg width="18" height="18" fill="none" stroke="var(--fg)" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" strokeWidth="2" strokeLinecap="round"/></svg>
          </button>
        )}
      </aside>
    </>
  );
};

// ── Main Dashboard ───────────────────────────────────────────────────────────
const Dashboard: React.FC = () => {
  const { isAuthenticated, logout, subscription, refreshSubscription } = useAuth();
  const navigate = useNavigate();

  // Core state
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [groupedConversations, setGroupedConversations] = useState<GroupedConversations>({ today: [], yesterday: [], lastWeek: [], older: [] });
  const [showUploadUI, setShowUploadUI] = useState(true);
  const [message, setMessage] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [error, setError] = useState('');

  // File upload
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [totalProgress, setTotalProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Presales
  const [showKickstartPanel, setShowKickstartPanel] = useState(false);
  const [kickstartAnswers, setKickstartAnswers] = useState<Record<string, string>>({});
  const [additionalContext, setAdditionalContext] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isPresalesChatting, setIsPresalesChatting] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<{
    readiness: ReadinessResult;
    contradictions: Contradiction[];
    vague_answers: VagueAnswer[];
    invalidated_questions: InvalidatedQuestion[];
    assumptions: Assumption[];
    follow_up_questions: Array<{ question_text: string; reason: string; priority: string }>;
    recommendations: string[];
    can_generate_report: boolean;
  } | null>(null);
  const [showReadinessModal, setShowReadinessModal] = useState(false);

  // Upgrade modal
  const [upgradeModal, setUpgradeModal] = useState<{ tier: 'basic' | 'plus' } | null>(null);
  const [isCheckingOut, setIsCheckingOut] = useState(false);

  // Streaming
  const { isStreaming, currentTool, toolStatus, thinkingMessage, toolsUsed, streamChat, cancelStream } = useStreamingChat();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Effects ──
  useEffect(() => {
    if (!isAuthenticated) navigate('/login');
    else {
      fetchConversations();
      const params = new URLSearchParams(window.location.search);
      if (params.get('upgrade') === 'success') {
        refreshSubscription();
        toast.success('Your plan has been upgraded!');
        window.history.replaceState({}, '', '/dashboard');
      }
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (messagesEndRef.current) {
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  }, [activeConversation?.messages, isSendingMessage]);

  // ── API helpers ──
  const fetchConversations = useCallback(async () => {
    try {
      const grouped = await conversationService.fetchConversations();
      setGroupedConversations(grouped);
    } catch { /* silent */ }
  }, []);

  const handleNewChat = () => {
    setActiveConversation(null);
    setShowUploadUI(true);
    setFiles([]);
    setMessage('');
    setError('');
    setKickstartAnswers({});
    setAdditionalContext('');
    setShowKickstartPanel(false);
    setAnalysisResult(null);
  };

  const handleSelectConversation = useCallback(async (chatHistoryId: string) => {
    setIsLoadingConversation(true);
    try {
      const response = await api.get(`/chat/${chatHistoryId}`);
      const details = response.data?.user_details;
      if (!details) return;

      let messages: Message[] = [];
      try {
        messages = typeof details.message === 'string' ? JSON.parse(details.message) : (details.message || []);
      } catch { messages = []; }

      const conv: Conversation = {
        id: details.chat_history_id,
        title: details.title,
        created_at: details.modified_at,
        messages,
        document_id: details.document_id || '',
        chat_history_id: details.chat_history_id,
        modified_at: details.modified_at,
        analysis_mode: details.analysis_mode,
        presales_id: details.presales_id,
      };

      if (conv.analysis_mode === 'presales' && conv.presales_id) {
        const presalesResp = await api.get(`/presales/${conv.presales_id}`);
        if (presalesResp.data?.presales_analysis) {
          const pa = presalesResp.data.presales_analysis;
          conv.p1_blockers = pa.p1_blockers || [];
          conv.kickstart_questions = pa.kickstart_questions || [];
          conv.blind_spots = pa.blind_spots;
        }
      }

      setActiveConversation(conv);
      setShowUploadUI(false);
      setKickstartAnswers({});

      if (isMobile) setSidebarExpanded(false);
    } catch {
      toast.error('Failed to load conversation');
    } finally {
      setIsLoadingConversation(false);
    }
  }, [isMobile]);

  const handleDeleteConversation = async (chatId: string) => {
    try {
      await conversationService.deleteConversation(chatId);
      await fetchConversations();
      if (activeConversation?.chat_history_id === chatId) handleNewChat();
      toast.success('Conversation deleted');
    } catch {
      toast.error('Failed to delete conversation');
    }
  };

  // ── File handling ──
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files).filter(file => {
        if (file.size > 10 * 1024 * 1024) { toast.error(`${file.name} exceeds 10MB limit`); return false; }
        const ext = file.name.split('.').pop()?.toLowerCase();
        const valid = ['pdf', 'ppt', 'pptx', 'docx', 'txt', 'csv'].includes(ext || '');
        if (!valid) { toast.error(`${file.name} is not a supported format`); return false; }
        return true;
      });
      setFiles(prev => [...prev, ...newFiles]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files);
      setFiles(prev => [...prev, ...newFiles]);
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) { setError('Please select a file to upload'); return; }

    // Check free tier limit
    if (subscription?.tier === 'free' && subscription.limits.max_chats !== null) {
      const chatCount = subscription.usage.chats;
      if (chatCount >= (subscription.limits.max_chats || 5)) {
        setUpgradeModal({ tier: 'basic' });
        return;
      }
    }

    setIsUploading(true);
    setTotalProgress(0);
    setError('');

    try {
      const formData = new FormData();
      files.forEach(f => formData.append('file', f));

      const resp = await api.post('/upload', formData, {
        onUploadProgress: (pe) => setTotalProgress(Math.round((pe.loaded * 100) / (pe.total || 1))),
      });

      setIsProcessing(true);

      const documentId = resp.data.document_id;
      const chatHistoryId = resp.data.chat_history_id || documentId;
      const analysisMode = resp.data.analysis_mode || 'presales';
      const presalesId = resp.data.presales_id;
      const chatTitle = resp.data.title || `Analysis of ${files[0].name}`;

      const initialMessage: Message = {
        role: 'assistant',
        content: resp.data.message || 'Analysis complete.',
        timestamp: new Date().toISOString(),
        selected: true,
      };

      const newConv: Conversation = {
        id: chatHistoryId,
        title: chatTitle,
        created_at: new Date().toISOString(),
        messages: [initialMessage],
        document_id: documentId || '',
        chat_history_id: chatHistoryId,
        modified_at: new Date().toISOString(),
        analysis_mode: analysisMode,
        presales_id: presalesId,
        p1_blockers: resp.data.p1_blockers || [],
        kickstart_questions: resp.data.kickstart_questions || resp.data.blind_spots?.critical_unknowns || [],
        blind_spots: resp.data.blind_spots,
      };

      setActiveConversation(newConv);
      setShowUploadUI(false);
      setFiles([]);
      await fetchConversations();
    } catch (err) {
      if (isAxiosError(err)) {
        const detail = err.response?.data?.detail || '';
        if (err.response?.status === 429 || detail.includes('limit')) {
          setUpgradeModal({ tier: 'basic' });
        } else {
          setError(detail || 'Upload failed. Please try again.');
        }
      } else {
        setError('Upload failed. Please try again.');
      }
    } finally {
      setIsUploading(false);
      setIsProcessing(false);
    }
  };

  // ── Messaging ──
  const handleSendMessage = async () => {
    if (!message.trim() || !activeConversation) return;

    const userMsg: Message = { role: 'user', content: message.trim(), timestamp: new Date().toISOString(), selected: true };
    const userId = localStorage.getItem('user_id') || '';
    const token = localStorage.getItem('access_token') || localStorage.getItem('regular_token') || '';

    setActiveConversation(prev => prev ? { ...prev, messages: [...prev.messages, userMsg] } : prev);
    setMessage('');
    setIsSendingMessage(true);

    if (USE_STREAMING && activeConversation.chat_history_id) {
      try {
        const allMsgs = [...(activeConversation.messages || []), userMsg];
        let streamedContent = '';

        const assistantPlaceholder: Message = { role: 'assistant', content: '', timestamp: new Date().toISOString() };
        setActiveConversation(prev => prev ? { ...prev, messages: [...prev.messages, assistantPlaceholder] } : prev);

        await streamChat({
          chatHistoryId: activeConversation.chat_history_id!,
          userId,
          messages: allMsgs,
          documentId: activeConversation.document_id,
          title: activeConversation.title,
          token,
          onToken: (_, accumulated) => {
            streamedContent = accumulated;
            setActiveConversation(prev => {
              if (!prev) return prev;
              const msgs = [...prev.messages];
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: accumulated };
              return { ...prev, messages: msgs };
            });
          },
          onComplete: (content) => {
            streamedContent = content;
            setActiveConversation(prev => {
              if (!prev) return prev;
              const msgs = [...prev.messages];
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content };
              return { ...prev, messages: msgs };
            });
            fetchConversations();
          },
          onError: (err) => {
            toast.error(err);
            setActiveConversation(prev => {
              if (!prev) return prev;
              const msgs = prev.messages.slice(0, -1);
              return { ...prev, messages: msgs };
            });
          },
        });
      } finally {
        setIsSendingMessage(false);
      }
    } else {
      try {
        const chatHistoryId = activeConversation.chat_history_id;
        const allMsgs = [...(activeConversation.messages || []), userMsg];

        const resp = await api.post('/chat-with-doc-v3', {
          chat_history_id: chatHistoryId,
          user_id: userId,
          message: allMsgs,
          document_id: activeConversation.document_id,
          title: activeConversation.title,
        });

        const content = resp.data?.message || resp.data?.response || '';
        const assistantMsg: Message = { role: 'assistant', content, timestamp: new Date().toISOString() };
        setActiveConversation(prev => prev ? { ...prev, messages: [...prev.messages, assistantMsg] } : prev);
        await fetchConversations();
      } catch (err) {
        if (isAxiosError(err) && err.response?.status === 429) setUpgradeModal({ tier: 'basic' });
        else toast.error('Failed to send message');
      } finally {
        setIsSendingMessage(false);
      }
    }
  };

  const handlePresalesChat = async () => {
    if (!message.trim() || !activeConversation?.chat_history_id) return;

    const userMsg: Message = { role: 'user', content: message.trim(), timestamp: new Date().toISOString() };
    setActiveConversation(prev => prev ? { ...prev, messages: [...prev.messages, userMsg] } : prev);
    setMessage('');
    setIsPresalesChatting(true);

    try {
      const resp = await api.post('/chat-with-doc-v3', {
        chat_history_id: activeConversation.chat_history_id,
        user_id: localStorage.getItem('user_id') || '',
        message: [...(activeConversation.messages || []), userMsg],
      });

      const content = resp.data?.message || resp.data?.response || '';
      const assistantMsg: Message = { role: 'assistant', content, timestamp: new Date().toISOString() };
      setActiveConversation(prev => prev ? { ...prev, messages: [...prev.messages, assistantMsg] } : prev);
    } catch {
      toast.error('Failed to send message');
    } finally {
      setIsPresalesChatting(false);
    }
  };

  // ── Presales analysis ──
  const handleSaveAndAnalyze = async () => {
    if (!activeConversation?.presales_id) return;
    setIsAnalyzing(true);

    try {
      const answers: Record<string, string> = {};
      (activeConversation.p1_blockers || []).forEach((_, i) => {
        if (kickstartAnswers[`p1_${i}`]) answers[`P1-${i + 1}`] = kickstartAnswers[`p1_${i}`];
      });
      (activeConversation.kickstart_questions || []).forEach((_, i) => {
        if (kickstartAnswers[`question_${i}`]) answers[`Q${i + 1}`] = kickstartAnswers[`question_${i}`];
      });

      await api.post(`/presales/${activeConversation.presales_id}/questions/answers`, { answers });
      const analyzeResp = await api.post(`/presales/${activeConversation.presales_id}/analyze`);

      setAnalysisResult(analyzeResp.data);
      setShowReadinessModal(true);
    } catch {
      toast.error('Analysis failed. Please try again.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleGenerateFullReport = async () => {
    if (!activeConversation?.presales_id) return;
    setIsProcessing(true);
    setShowReadinessModal(false);

    try {
      const answers: Record<string, string> = {};
      (activeConversation.p1_blockers || []).forEach((_, i) => {
        if (kickstartAnswers[`p1_${i}`]) answers[`P1-${i + 1}`] = kickstartAnswers[`p1_${i}`];
      });
      (activeConversation.kickstart_questions || []).forEach((_, i) => {
        if (kickstartAnswers[`question_${i}`]) answers[`Q${i + 1}`] = kickstartAnswers[`question_${i}`];
      });

      const resp = await api.post('/generate-full-report/', {
        presales_id: activeConversation.presales_id,
        user_answers: answers,
        assumptions: analysisResult?.assumptions || [],
        additional_context: additionalContext,
      });

      const content = resp.data?.report_content || resp.data?.message || '';
      const assistantMsg: Message = { role: 'assistant', content, timestamp: new Date().toISOString() };
      setActiveConversation(prev => prev ? { ...prev, messages: [...(prev.messages || []), assistantMsg], analysis_mode: 'full' } : prev);
      await fetchConversations();
      toast.success('Full report generated!');
    } catch {
      toast.error('Report generation failed. Please try again.');
    } finally {
      setIsProcessing(false);
    }
  };

  // ── Checkout ──
  const handleUpgrade = async (tier: 'basic' | 'plus') => {
    setIsCheckingOut(true);
    try {
      const { checkout_url } = await createCheckoutSession(tier);
      window.location.href = checkout_url;
    } catch {
      toast.error('Could not start checkout. Please try again.');
    } finally {
      setIsCheckingOut(false);
    }
  };

  // ── Textarea auto-resize ──
  const handleMessageChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  const isPresales = activeConversation?.analysis_mode === 'presales';
  const isFull = activeConversation?.analysis_mode === 'full';
  const sidebarOffset = sidebarExpanded ? 256 : (isMobile ? 0 : 56);

  // ── Render ──
  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg)', overflow: 'hidden' }}>
      <Sidebar
        expanded={sidebarExpanded}
        toggle={() => setSidebarExpanded(p => !p)}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        activeId={activeConversation?.chat_history_id || null}
        grouped={groupedConversations}
        logout={logout}
        isMobile={isMobile}
        onDelete={handleDeleteConversation}
      />

      {/* main content */}
      <main
        style={{
          flex: 1,
          marginLeft: sidebarOffset,
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          overflow: 'hidden',
          transition: 'margin-left 0.25s ease',
        }}
      >
        {/* top bar */}
        <div
          style={{
            flexShrink: 0,
            height: 52,
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px',
            background: 'var(--surface)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {activeConversation && (
              <span style={{ fontSize: 14, color: 'var(--fg-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 300 }}>
                {activeConversation.title}
              </span>
            )}
            {isPresales && (
              <span className="badge badge-accent" style={{ fontSize: 10 }}>PRESALES</span>
            )}
            {isFull && (
              <span className="badge badge-ok" style={{ fontSize: 10 }}>FULL REPORT</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {subscription && (
              <span className="label-mono" style={{ fontSize: 9, color: 'var(--fg-muted)' }}>
                {subscription.tier.toUpperCase()} · {subscription.usage.chats}/{subscription.limits.max_chats ?? '∞'} chats
              </span>
            )}
            {subscription?.tier === 'free' && (
              <button
                onClick={() => setUpgradeModal({ tier: 'basic' })}
                className="btn btn-primary"
                style={{ padding: '4px 10px', fontSize: 11 }}
              >
                Upgrade
              </button>
            )}
          </div>
        </div>

        {/* body */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {showUploadUI ? (
            /* ── Upload UI ── */
            <div
              style={{ flex: 1, overflowY: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
              className="bg-grid"
            >
              <div style={{ width: '100%', maxWidth: 600 }}>
                <div style={{ textAlign: 'center', marginBottom: 32 }}>
                  <p className="label-mono" style={{ marginBottom: 10 }}>DOCUMENT ANALYSIS</p>
                  <h1 className="font-display" style={{ fontSize: 'clamp(1.8rem, 4vw, 2.8rem)', fontWeight: 400, margin: '0 0 12px', color: 'var(--fg)' }}>
                    Upload your document
                  </h1>
                  <p style={{ fontSize: 15, color: 'var(--fg-dim)', margin: 0 }}>
                    PDF, PPTX, DOCX, TXT — get risks, questions, architecture, and timeline in minutes.
                  </p>
                </div>

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                  {/* drop zone */}
                  {files.length === 0 ? (
                    <div
                      onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
                      onDragLeave={() => setIsDragging(false)}
                      onDrop={handleDrop}
                      onClick={() => fileInputRef.current?.click()}
                      style={{
                        padding: '48px 32px',
                        textAlign: 'center',
                        border: `2px dashed ${isDragging ? 'var(--accent)' : 'var(--border-strong)'}`,
                        borderRadius: 12,
                        cursor: 'pointer',
                        background: isDragging ? 'var(--accent-soft2)' : 'transparent',
                        transition: 'all 0.15s',
                      }}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        style={{ display: 'none' }}
                        onChange={handleFileChange}
                        accept=".pdf,.ppt,.pptx,.docx,.txt,.csv"
                        multiple
                      />
                      <div style={{ fontSize: 32, marginBottom: 12 }}>📄</div>
                      <p style={{ fontSize: 15, fontWeight: 500, color: 'var(--fg)', margin: '0 0 6px' }}>
                        Drag and drop your files here
                      </p>
                      <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: '0 0 16px' }}>or click to browse</p>
                      <span className="badge badge-accent" style={{ fontSize: 10 }}>PDF · PPTX · DOCX · TXT · CSV</span>
                    </div>
                  ) : (
                    <div style={{ padding: 20 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)', margin: 0 }}>
                          {files.length} file{files.length > 1 ? 's' : ''} selected
                        </p>
                        <button
                          onClick={() => setFiles([])}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', fontSize: 12 }}
                        >
                          Clear all
                        </button>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16, maxHeight: 160, overflowY: 'auto' }}>
                        {files.map((f, i) => (
                          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 6, border: '1px solid var(--border)' }}>
                            <span style={{ fontSize: 14, flexShrink: 0 }}>📄</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <p style={{ margin: 0, fontSize: 13, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</p>
                              <p style={{ margin: 0, fontSize: 11, color: 'var(--fg-muted)' }}>{(f.size / 1024).toFixed(1)} KB</p>
                            </div>
                            <button
                              onClick={() => setFiles(prev => prev.filter((_, j) => j !== i))}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', padding: 2, lineHeight: 0 }}
                            >
                              <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" strokeWidth="2" strokeLinecap="round"/></svg>
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {files.length > 0 && (
                    <div style={{ padding: '0 20px 20px' }}>
                      {error && (
                        <p style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 10 }}>{error}</p>
                      )}
                      {isUploading && (
                        <div style={{ marginBottom: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 11, color: 'var(--fg-muted)' }}>
                            <span>Uploading…</span>
                            <span>{totalProgress}%</span>
                          </div>
                          <div style={{ height: 3, background: 'var(--border-strong)', borderRadius: 2 }}>
                            <div style={{ height: '100%', width: `${totalProgress}%`, background: 'var(--accent)', borderRadius: 2, transition: 'width 0.2s' }} />
                          </div>
                        </div>
                      )}
                      {isProcessing && !isUploading && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px', background: 'var(--accent-soft)', borderRadius: 8, marginBottom: 12, fontSize: 13, color: 'var(--accent)' }}>
                          <div className="animate-spin" style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid var(--accent)', borderTopColor: 'transparent' }} />
                          AI agents are analysing your document…
                        </div>
                      )}
                      <button
                        className="btn btn-primary"
                        onClick={handleUpload}
                        disabled={isUploading || isProcessing}
                        style={{ width: '100%', justifyContent: 'center', padding: '12px', fontSize: 14, opacity: (isUploading || isProcessing) ? 0.7 : 1 }}
                      >
                        {isUploading ? 'Uploading…' : isProcessing ? 'Analysing…' : 'Analyse document →'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* ── Chat area ── */
            <>
              {/* messages */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
                {isLoadingConversation ? (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: 32, color: 'var(--fg-muted)', fontSize: 13, gap: 8 }}>
                    <div className="animate-spin" style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid var(--accent)', borderTopColor: 'transparent' }} />
                    Loading…
                  </div>
                ) : (
                  <div style={{ maxWidth: 800, margin: '0 auto', padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {(activeConversation?.messages || []).map((msg, i) => {
                      const isUser = msg.role === 'user';
                      const isLastAssistant = !isUser && i === (activeConversation?.messages?.length || 0) - 1;
                      const showStreaming = isLastAssistant && (isStreaming || isSendingMessage);

                      return (
                        <div key={i} style={{ display: 'flex', gap: 12, flexDirection: isUser ? 'row-reverse' : 'row' }}>
                          {/* avatar */}
                          <div
                            style={{
                              width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                              background: isUser ? 'var(--accent-soft)' : 'var(--surface-2)',
                              border: `1px solid ${isUser ? 'rgba(255,138,101,0.3)' : 'var(--border)'}`,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontSize: 12, color: isUser ? 'var(--accent)' : 'var(--fg-muted)',
                              fontWeight: 600,
                            }}
                          >
                            {isUser ? 'U' : 'A'}
                          </div>

                          {/* bubble */}
                          <div
                            style={{
                              maxWidth: '75%',
                              padding: '10px 14px',
                              borderRadius: isUser ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
                              background: isUser ? 'var(--accent-soft)' : 'var(--surface)',
                              border: `1px solid ${isUser ? 'rgba(255,138,101,0.2)' : 'var(--border)'}`,
                              fontSize: 14,
                              color: 'var(--fg)',
                              lineHeight: 1.6,
                            }}
                          >
                            {showStreaming ? (
                              <StreamingMsg
                                content={msg.content}
                                isStreaming={isStreaming}
                                currentTool={currentTool}
                                toolStatus={toolStatus}
                                thinkingMessage={thinkingMessage}
                                toolsUsed={toolsUsed}
                              />
                            ) : isUser ? (
                              <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.content}</p>
                            ) : (
                              <MessageContent content={msg.content} />
                            )}
                          </div>
                        </div>
                      );
                    })}

                    {/* streaming empty placeholder */}
                    {(isStreaming || isSendingMessage) && !activeConversation?.messages?.some(m => m.role === 'assistant') && (
                      <div style={{ display: 'flex', gap: 12 }}>
                        <div style={{ width: 32, height: 32, borderRadius: '50%', flexShrink: 0, background: 'var(--surface-2)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: 'var(--fg-muted)', fontWeight: 600 }}>A</div>
                        <div style={{ padding: '10px 14px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '4px 12px 12px 12px' }}>
                          <StreamingMsg content="" isStreaming thinkingMessage={thinkingMessage} currentTool={currentTool} toolStatus={toolStatus} />
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              {/* presales questions panel */}
              {isPresales && showKickstartPanel && (
                <div style={{ flexShrink: 0, borderTop: '1px solid var(--border)', background: 'var(--surface)', maxHeight: 300, overflowY: 'auto' }}>
                  <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>
                      P1 Blockers & Kickstart Questions
                    </p>
                    <button
                      onClick={handleSaveAndAnalyze}
                      disabled={isAnalyzing}
                      className="btn btn-primary"
                      style={{ padding: '5px 12px', fontSize: 12, opacity: isAnalyzing ? 0.7 : 1 }}
                    >
                      {isAnalyzing ? 'Analysing…' : 'Save & Analyse'}
                    </button>
                  </div>
                  <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {(activeConversation?.p1_blockers || []).map((p, i) => (
                      <div key={i} style={{ padding: '10px 12px', background: 'rgba(248,113,113,0.05)', border: '1px solid rgba(248,113,113,0.15)', borderRadius: 8 }}>
                        <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                          <span className="badge" style={{ background: 'rgba(248,113,113,0.12)', color: 'var(--danger)', flexShrink: 0 }}>P1-{i + 1}</span>
                          <span style={{ fontSize: 13, color: 'var(--fg)', fontWeight: 500 }}>{p.blocker}</span>
                        </div>
                        <p style={{ margin: '0 0 6px', fontSize: 12, color: 'var(--fg-muted)' }}>{p.question}</p>
                        <textarea
                          placeholder={`Answer for P1-${i + 1}…`}
                          value={kickstartAnswers[`p1_${i}`] || ''}
                          onChange={e => setKickstartAnswers(prev => ({ ...prev, [`p1_${i}`]: e.target.value }))}
                          className="input"
                          style={{ resize: 'none', fontSize: 12, padding: '6px 10px', marginTop: 4 }}
                          rows={2}
                        />
                      </div>
                    ))}
                    {(activeConversation?.kickstart_questions || []).map((q, i) => (
                      <div key={i} style={{ padding: '10px 12px', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8 }}>
                        <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                          <span className="badge badge-accent" style={{ flexShrink: 0 }}>Q{i + 1}</span>
                          <span style={{ fontSize: 13, color: 'var(--fg)' }}>{q.question}</span>
                        </div>
                        <textarea
                          placeholder={`Answer for Q${i + 1}…`}
                          value={kickstartAnswers[`question_${i}`] || ''}
                          onChange={e => setKickstartAnswers(prev => ({ ...prev, [`question_${i}`]: e.target.value }))}
                          className="input"
                          style={{ resize: 'none', fontSize: 12, padding: '6px 10px', marginTop: 4 }}
                          rows={2}
                        />
                      </div>
                    ))}
                    <div style={{ paddingTop: 8, borderTop: '1px solid var(--border)' }}>
                      <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: '0 0 6px' }}>Additional context (optional)</p>
                      <textarea
                        placeholder="Notes from client calls, emails, or any additional context…"
                        value={additionalContext}
                        onChange={e => setAdditionalContext(e.target.value)}
                        className="input"
                        style={{ resize: 'none', fontSize: 12, padding: '8px 10px' }}
                        rows={3}
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* chat input */}
              <div style={{ flexShrink: 0, borderTop: '1px solid var(--border)', background: 'var(--surface)', padding: '12px 16px' }}>
                {/* presales toolbar */}
                {isPresales && (
                  <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                    <span className="badge badge-accent" style={{ fontSize: 10 }}>PRE-SALES</span>
                    <button
                      onClick={() => setShowKickstartPanel(p => !p)}
                      className={`btn ${showKickstartPanel ? 'btn-primary' : 'btn-ghost'}`}
                      style={{ padding: '4px 10px', fontSize: 11 }}
                    >
                      Questions {((activeConversation?.p1_blockers?.length || 0) + (activeConversation?.kickstart_questions?.length || 0)) > 0 && `(${(activeConversation?.p1_blockers?.length || 0) + (activeConversation?.kickstart_questions?.length || 0)})`}
                    </button>
                    <button
                      onClick={handleGenerateFullReport}
                      disabled={isProcessing}
                      className="btn btn-primary"
                      style={{ padding: '4px 10px', fontSize: 11, opacity: isProcessing ? 0.7 : 1 }}
                    >
                      {isProcessing ? 'Generating…' : 'Generate Full Report'}
                    </button>
                  </div>
                )}

                <div style={{ position: 'relative', maxWidth: 800, margin: '0 auto' }}>
                  <textarea
                    ref={textareaRef}
                    value={message}
                    onChange={handleMessageChange}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (isPresales) handlePresalesChat();
                        else handleSendMessage();
                      }
                    }}
                    placeholder={isPresales ? 'Ask about the analysis (e.g., "Tell me more about P1-2")…' : 'Type your message…'}
                    style={{
                      width: '100%',
                      padding: '10px 48px 10px 14px',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 10,
                      color: 'var(--fg)',
                      fontSize: 14,
                      fontFamily: '"Inter Tight", sans-serif',
                      resize: 'none',
                      outline: 'none',
                      minHeight: 44,
                      maxHeight: 120,
                      lineHeight: 1.5,
                      overflowY: 'auto',
                    }}
                    rows={1}
                  />
                  <button
                    onClick={isPresales ? handlePresalesChat : handleSendMessage}
                    disabled={!message.trim() || isSendingMessage || isPresalesChatting || isStreaming}
                    style={{
                      position: 'absolute', right: 8, bottom: 8,
                      width: 32, height: 32, borderRadius: '50%',
                      background: message.trim() && !isSendingMessage ? 'var(--accent)' : 'var(--surface-3)',
                      border: 'none', cursor: message.trim() && !isSendingMessage ? 'pointer' : 'not-allowed',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: message.trim() ? '#1a0a04' : 'var(--fg-muted)',
                      transition: 'background 0.15s',
                    }}
                  >
                    {(isSendingMessage || isPresalesChatting || isStreaming) ? (
                      <div className="animate-spin" style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid currentColor', borderTopColor: 'transparent' }} />
                    ) : (
                      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 20 20"><path d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" fill="currentColor"/></svg>
                    )}
                  </button>
                  {isStreaming && (
                    <button
                      onClick={cancelStream}
                      style={{ position: 'absolute', right: 48, bottom: 8, padding: '4px 8px', background: 'none', border: '1px solid var(--border-strong)', borderRadius: 6, color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 11 }}
                    >
                      Stop
                    </button>
                  )}
                </div>
                <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--fg-muted)', marginTop: 6 }}>
                  Enter to send · Shift+Enter for new line
                </p>
              </div>
            </>
          )}
        </div>
      </main>

      {/* ── Readiness modal ── */}
      {showReadinessModal && analysisResult && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', padding: 16 }}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 16, width: '100%', maxWidth: 560, maxHeight: '90vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--fg)' }}>Readiness Analysis</h3>
              <button onClick={() => setShowReadinessModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', lineHeight: 0, padding: 4 }}>
                <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" strokeWidth="2" strokeLinecap="round"/></svg>
              </button>
            </div>
            <div style={{ overflowY: 'auto', padding: '16px 20px', flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* score */}
              <div style={{ padding: 16, background: 'var(--surface-2)', borderRadius: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontSize: 13, color: 'var(--fg-dim)' }}>Readiness Score</span>
                  <span className="font-display" style={{ fontSize: 22, fontWeight: 400, color: analysisResult.readiness.score >= 0.8 ? 'var(--ok)' : analysisResult.readiness.score >= 0.5 ? 'var(--warn)' : 'var(--danger)' }}>
                    {Math.round(analysisResult.readiness.score * 100)}%
                  </span>
                </div>
                <div style={{ height: 6, background: 'var(--border-strong)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${analysisResult.readiness.score * 100}%`, background: analysisResult.readiness.score >= 0.8 ? 'var(--ok)' : analysisResult.readiness.score >= 0.5 ? 'var(--warn)' : 'var(--danger)', transition: 'width 0.5s', borderRadius: 3 }} />
                </div>
                {analysisResult.readiness.summary && (
                  <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--fg-dim)', lineHeight: 1.5 }}>{analysisResult.readiness.summary}</p>
                )}
              </div>

              {/* issues */}
              {analysisResult.contradictions.length > 0 && (
                <div>
                  <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--danger)', margin: '0 0 8px' }}>Contradictions ({analysisResult.contradictions.length})</p>
                  {analysisResult.contradictions.map((c, i) => (
                    <div key={i} style={{ padding: '10px 12px', background: 'rgba(248,113,113,0.06)', border: '1px solid rgba(248,113,113,0.15)', borderRadius: 8, marginBottom: 6 }}>
                      <p style={{ margin: '0 0 4px', fontSize: 13, color: 'var(--fg)', fontWeight: 500 }}>{c.description}</p>
                      <p style={{ margin: '0 0 4px', fontSize: 12, color: 'var(--fg-muted)' }}>{c.explanation}</p>
                      <p style={{ margin: 0, fontSize: 12, color: 'var(--warn)' }}>Fix: {c.suggested_resolution}</p>
                    </div>
                  ))}
                </div>
              )}

              {analysisResult.assumptions.length > 0 && (
                <div>
                  <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', margin: '0 0 8px' }}>Assumptions to be made ({analysisResult.assumptions.length})</p>
                  {analysisResult.assumptions.map((a, i) => (
                    <div key={i} style={{ padding: '10px 12px', background: 'var(--accent-soft2)', border: '1px solid rgba(255,138,101,0.1)', borderRadius: 8, marginBottom: 6, display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <div>
                        <p style={{ margin: '0 0 2px', fontSize: 13, color: 'var(--fg)' }}>{a.assumption}</p>
                        <p style={{ margin: 0, fontSize: 11, color: 'var(--fg-muted)' }}>For: {a.for_question_id}</p>
                      </div>
                      <span className="badge" style={{ background: a.risk_level === 'high' ? 'rgba(248,113,113,0.12)' : a.risk_level === 'medium' ? 'rgba(251,191,36,0.12)' : 'rgba(74,222,128,0.12)', color: a.risk_level === 'high' ? 'var(--danger)' : a.risk_level === 'medium' ? 'var(--warn)' : 'var(--ok)', flexShrink: 0, height: 'fit-content' }}>
                        {a.risk_level}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, justifyContent: 'flex-end', flexShrink: 0 }}>
              <button onClick={() => setShowReadinessModal(false)} className="btn btn-ghost" style={{ fontSize: 13 }}>Back to Edit</button>
              {analysisResult.contradictions.length === 0 && (
                <button
                  onClick={handleGenerateFullReport}
                  disabled={!analysisResult.can_generate_report}
                  className="btn btn-primary"
                  style={{ fontSize: 13, opacity: analysisResult.can_generate_report ? 1 : 0.5 }}
                >
                  Generate Full Report →
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Upgrade modal ── */}
      {upgradeModal && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', padding: 16 }}>
          <div style={{ background: 'var(--surface)', border: '1px solid rgba(255,138,101,0.3)', borderRadius: 16, width: '100%', maxWidth: 400, padding: 28 }}>
            <div style={{ textAlign: 'center', marginBottom: 24 }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>🚀</div>
              <h3 className="font-display" style={{ fontSize: 22, fontWeight: 400, margin: '0 0 8px', color: 'var(--fg)' }}>Upgrade your plan</h3>
              <p style={{ fontSize: 14, color: 'var(--fg-dim)', margin: 0 }}>
                You've reached your free tier limit. Upgrade to unlock unlimited conversations and full reports.
              </p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button
                onClick={() => handleUpgrade('basic')}
                disabled={isCheckingOut}
                className="btn btn-primary"
                style={{ justifyContent: 'center', padding: '12px', fontSize: 14, opacity: isCheckingOut ? 0.7 : 1 }}
              >
                {isCheckingOut ? 'Redirecting…' : 'Upgrade to Basic — $29/mo'}
              </button>
              <button
                onClick={() => handleUpgrade('plus')}
                disabled={isCheckingOut}
                className="btn btn-ghost"
                style={{ justifyContent: 'center', padding: '12px', fontSize: 14 }}
              >
                Upgrade to Plus — $79/mo
              </button>
              <button
                onClick={() => setUpgradeModal(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-muted)', fontSize: 13, padding: '6px', textAlign: 'center' }}
              >
                Maybe later
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
