import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { fetchOverview } from '../services/projectsService';
import * as conversationService from '../services/conversationService';
import type { OverviewResponse } from '../types/overview';
import type { GroupedConversations } from '../types/conversation';
import Sidebar from '../components/sidebar/Sidebar';
import TotalProjectsTile from '../components/overview/TotalProjectsTile';
import ReadinessTile from '../components/overview/ReadinessTile';
import PlanTile from '../components/overview/PlanTile';
import ProjectsGrid from '../components/overview/ProjectsGrid';
import QuestionsInbox from '../components/overview/QuestionsInbox';
import { surface, text, accent } from '../styles/tokens';

const emptyGrouped: GroupedConversations = {
  today: [],
  yesterday: [],
  lastWeek: [],
  older: [],
};

export default function ProjectsOverview() {
  const navigate = useNavigate();
  const { isAuthenticated, logout } = useAuth();

  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [grouped, setGrouped] = useState<GroupedConversations>(emptyGrouped);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    const onResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setSidebarExpanded(false);
    };
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const g = await conversationService.fetchConversations();
      setGrouped(g);
    } catch (e) {
      console.error('Failed to load conversations', e);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [ov] = await Promise.all([fetchOverview(), refreshConversations()]);
        if (!cancelled) setOverview(ov);
      } catch (e: any) {
        console.error('Failed to load overview', e);
        if (!cancelled) setError('Failed to load projects overview.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, refreshConversations]);

  const handleSelectConversation = (conv: { chat_history_id?: string; id?: string }) => {
    const id = conv.chat_history_id || conv.id;
    if (id) navigate(`/dashboard/${id}`);
  };

  const handleSelectConversationById = async (chatHistoryId: string) => {
    navigate(`/dashboard/${chatHistoryId}`);
  };

  const handleNewChat = () => navigate('/dashboard');

  return (
    <div className={`min-h-screen ${surface.pageGradient} ${text.primary} flex`}>
      <Sidebar
        expanded={sidebarExpanded}
        toggleExpanded={() => setSidebarExpanded(v => !v)}
        onSelectConversation={handleSelectConversation}
        onSelectConversationById={handleSelectConversationById}
        onNewChat={handleNewChat}
        logout={logout}
        isMobile={isMobile}
        activeConversationId={null}
        groupedConversations={grouped}
        onRefreshConversations={refreshConversations}
      />

      <main className="flex-1 min-w-0 overflow-y-auto">
        <div className="px-4 md:px-8 py-6 max-w-[1600px] mx-auto">
          {/* Header */}
          <div className="flex items-start justify-between mb-6 gap-4">
            <div>
              <h1 className={`text-2xl md:text-3xl font-bold ${accent.textGradient}`}>
                Your Projects
              </h1>
              <p className={`text-sm ${text.muted} mt-1`}>
                Portfolio snapshot, readiness, and unanswered questions across all analyses.
              </p>
            </div>
            <button
              type="button"
              onClick={handleNewChat}
              className={`shrink-0 px-4 py-2 rounded-lg text-sm font-semibold text-white ${accent.actionGradient} ${accent.actionHover} shadow-md transition-all duration-200 hover:shadow-purple-500/30`}
            >
              + New Project
            </button>
          </div>

          {loading && (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin h-10 w-10 border-4 border-white/20 border-t-purple-400 rounded-full" />
            </div>
          )}

          {error && !loading && (
            <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
              {error}
            </div>
          )}

          {!loading && !error && overview && (
            <>
              {/* KPI row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-4 mb-6">
                <TotalProjectsTile kpis={overview.kpis} />
                <ReadinessTile kpis={overview.kpis} />
                <PlanTile subscription={overview.subscription} />
              </div>

              {/* Two-column split */}
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 md:gap-6">
                <div className="xl:col-span-2 min-w-0">
                  <ProjectsGrid projects={overview.projects} />
                </div>
                <div className="min-w-0">
                  <QuestionsInbox inbox={overview.questions_inbox} />
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
