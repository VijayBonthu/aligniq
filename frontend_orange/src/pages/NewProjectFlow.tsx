import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import api from '../services/api';
import * as presalesService from '../services/presalesService';
import { startFullPipeline } from '../services/fullPipelineService';
import type { PipelineStatus } from '../services/fullPipelineService';
import type { UploadPresalesResponse } from '../services/uploadService';
import WizardStepper, { type WizardPhase } from '../components/newproject/WizardStepper';
import UploadStep from '../components/newproject/UploadStep';
import QuestionsStep, { type PresalesQuestion } from '../components/newproject/QuestionsStep';
import AnalysisStep, { type AnalysisAssumption } from '../components/newproject/AnalysisStep';
import ReportStep from '../components/newproject/ReportStep';
import { answerKeyForDisplayId } from '../utils/questionKey';
import { useAuth } from '../context/AuthContext';

const ASSUMPTION_TAG = '[SYSTEM ASSUMPTION]';

interface ChatRecordResponse {
  user_details?: {
    chat_history_id: string;
    document_id: string | null;
    title: string | null;
    analysis_mode?: 'presales' | 'full';
    presales_id?: string | null;
    message?: string | unknown;
    pipeline_status?: PipelineStatus;
  };
}

export default function NewProjectFlow() {
  const navigate = useNavigate();
  const { chatHistoryId: urlChatHistoryId } = useParams<{ chatHistoryId?: string }>();
  const { subscription, showLimitHit } = useAuth();

  const checkChatLimit = (): boolean => {
    if (subscription && subscription.limits.max_chats !== null
        && subscription.usage.chats >= subscription.limits.max_chats) {
      showLimitHit({
        limit_type: 'max_chats',
        current: subscription.usage.chats,
        limit: subscription.limits.max_chats,
      });
      return false;
    }
    return true;
  };

  const [phase, setPhase] = useState<WizardPhase>('upload');
  const [uploadData, setUploadData] = useState<UploadPresalesResponse | null>(null);
  const [questions, setQuestions] = useState<PresalesQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [additionalContext, setAdditionalContext] = useState('');
  const [generating, setGenerating] = useState(false);
  const [reportContent, setReportContent] = useState<string | null>(null);
  const [chatHistoryIdState, setChatHistoryIdState] = useState<string | null>(null);
  const [projectTitle, setProjectTitle] = useState<string>('New project');
  const [hydrating, setHydrating] = useState<boolean>(Boolean(urlChatHistoryId));

  const initialQuestions: PresalesQuestion[] = useMemo(() => {
    if (!uploadData) return [];
    return [
      ...((uploadData.p1_blockers as PresalesQuestion[] | undefined) ?? []).map((b) => ({
        ...b,
        question_type: 'p1' as const,
      })),
      ...((uploadData.kickstart_questions as PresalesQuestion[] | undefined) ?? []).map((q) => ({
        ...q,
        question_type: 'kickstart' as const,
      })),
    ];
  }, [uploadData]);

  // Hydrate from URL param when resuming an existing project.
  useEffect(() => {
    if (!urlChatHistoryId) {
      setHydrating(false);
      return;
    }

    let cancelled = false;
    (async () => {
      setHydrating(true);
      try {
        const { data } = await api.get<ChatRecordResponse>(`/chat/${urlChatHistoryId}`);
        const details = data.user_details;
        if (cancelled || !details) {
          throw new Error('Project not found');
        }

        if (details.pipeline_status === 'running' || details.pipeline_status === 'queued') {
          navigate(`/full-pipeline/${urlChatHistoryId}`, { replace: true });
          return;
        }

        if (details.analysis_mode === 'full' || details.pipeline_status === 'completed') {
          // Defensive: caller landed on /new-project/:id but the project is
          // already past full-report generation. Send them to the chat view.
          navigate(`/chat/${urlChatHistoryId}`, { replace: true });
          return;
        }

        const presalesId = details.presales_id || null;
        const documentId = details.document_id || null;
        if (!presalesId || !documentId) {
          throw new Error('Project missing presales metadata');
        }

        setProjectTitle(details.title || 'New project');
        setUploadData({
          presales_id: presalesId,
          document_id: documentId,
          chat_history_id: details.chat_history_id,
        });
        setChatHistoryIdState(details.chat_history_id);

        const [briefRes, questionsRes] = await Promise.allSettled([
          api.get(`/presales/${documentId}`),
          presalesService.getQuestions(presalesId),
        ]);

        if (cancelled) return;

        let hydratedQuestions: PresalesQuestion[] = [];
        if (questionsRes.status === 'fulfilled') {
          const raw = questionsRes.value;
          const arr: PresalesQuestion[] = Array.isArray(raw)
            ? raw
            : Array.isArray((raw as { questions?: PresalesQuestion[] })?.questions)
            ? (raw as { questions: PresalesQuestion[] }).questions
            : [];
          hydratedQuestions = arr;
          setQuestions(arr);

          const restored: Record<string, string> = {};
          const p1Items: PresalesQuestion[] = [];
          const kItems: PresalesQuestion[] = [];
          for (const q of arr) {
            const t = q.question_type;
            if (t === 'p1' || t === 'p1_blocker' || q.blocker) p1Items.push(q);
            else kItems.push(q);
          }
          p1Items.forEach((q, i) => {
            const key = answerKeyForDisplayId(q.question_number) || `p1_${i}`;
            if (q.answer) restored[key] = q.answer;
          });
          kItems.forEach((q, i) => {
            const key = answerKeyForDisplayId(q.question_number) || `question_${i}`;
            if (q.answer) restored[key] = q.answer;
          });
          setAnswers(restored);
        }
        if (briefRes.status === 'rejected') {
          // Brief is optional for the wizard; analysis step will recompute.
          console.warn('Failed to fetch presales brief during hydrate', briefRes.reason);
        }

        // Decide initial phase: if anything unanswered, send them back to questions.
        const anyUnanswered = hydratedQuestions.some((q) => !q.answer || !String(q.answer).trim());
        setPhase(anyUnanswered || hydratedQuestions.length === 0 ? 'questions' : 'analysis');
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to hydrate project', err);
        const detail =
          (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
          (err instanceof Error ? err.message : 'Project not found');
        toast.error(detail);
        navigate('/projects', { replace: true });
      } finally {
        if (!cancelled) setHydrating(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [urlChatHistoryId, navigate]);

  const handleApplyAssumptions = (assumptions: AnalysisAssumption[]) => {
    if (!assumptions.length) {
      setPhase('questions');
      return;
    }
    let applied = 0;
    setAnswers((prev) => {
      const next = { ...prev };
      for (const a of assumptions) {
        const key = answerKeyForDisplayId(a.for_question_id);
        const text = a.assumption || a.text;
        if (!key || !text) continue;
        const tagged = `${ASSUMPTION_TAG} ${text}`;
        const cur = next[key]?.trim();
        next[key] = !cur ? tagged : `${cur}\n\n${tagged}`;
        applied += 1;
      }
      return next;
    });
    if (applied > 0) {
      toast.success(
        `Applied ${applied} assumption${applied === 1 ? '' : 's'}. Review and edit, then Save & Analyse again.`,
      );
    } else {
      toast.error('Could not map assumptions to question fields.');
    }
    setPhase('questions');
  };

  const checkRegenLimit = (): boolean => {
    if (subscription && subscription.limits.monthly_report_regen !== null
        && subscription.usage.report_regenerations_used >= subscription.limits.monthly_report_regen) {
      showLimitHit({
        limit_type: 'monthly_report_regen',
        current: subscription.usage.report_regenerations_used,
        limit: subscription.limits.monthly_report_regen,
      });
      return false;
    }
    return true;
  };

  const handleGenerateReport = async (assumptions: AnalysisAssumption[]) => {
    if (!uploadData?.presales_id) return;
    if (!checkRegenLimit()) return;
    setGenerating(true);
    try {
      const res = await presalesService.generatePresalesReport(
        uploadData.presales_id,
        Object.keys(answers).length ? JSON.stringify(answers) : undefined,
        assumptions.length ? JSON.stringify(assumptions) : undefined,
        additionalContext.trim() || undefined,
      );
      const chatId = res.chat_history_id || uploadData.chat_history_id;
      const content = res.report || '';
      setChatHistoryIdState(chatId);
      setReportContent(content);
      toast.success('Presales brief ready.');
      setPhase('report');
      // Make the URL bookmarkable now that we have a stable chat_history_id.
      if (chatId && chatId !== urlChatHistoryId) {
        navigate(`/new-project/${chatId}`, { replace: true });
      }
    } catch (err: unknown) {
      // 402 quota errors are surfaced by the global UpgradeModal; don't double-toast.
      if (isAxiosError(err) && err.response?.status === 402) {
        return;
      }
      const detail =
        (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
        (err instanceof Error ? err.message : 'Failed to generate report.');
      toast.error(detail);
    } finally {
      setGenerating(false);
    }
  };

  const handleOpenChat = async () => {
    if (!chatHistoryIdState) {
      toast.error('Missing chat reference.');
      return;
    }
    if (!checkRegenLimit()) return;
    try {
      await startFullPipeline(chatHistoryIdState);
      navigate(`/full-pipeline/${chatHistoryIdState}`);
    } catch (err) {
      // 402 quota errors handled by global UpgradeModal.
      if (isAxiosError(err) && err.response?.status === 402) return;
      const detail =
        (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
        (err instanceof Error ? err.message : 'Failed to start pipeline.');
      toast.error(detail);
    }
  };

  if (hydrating) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div
        style={{
          flexShrink: 0,
          height: 52,
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 28px',
          background: 'var(--surface)',
          gap: 16,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--fg-muted)',
            letterSpacing: '.1em',
            textTransform: 'uppercase',
          }}
        >
          {urlChatHistoryId ? projectTitle : 'New project'}
        </span>
        <div style={{ flex: 1 }} />
        <WizardStepper phase={phase} />
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={() => navigate('/projects')}
          style={{
            padding: '6px 12px',
            background: 'transparent',
            border: '1px solid var(--border-strong)',
            borderRadius: 8,
            color: 'var(--fg-dim)',
            fontSize: 12,
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          ← Projects
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {phase === 'upload' && (
          <UploadStep
            onBeforeUpload={checkChatLimit}
            onComplete={(res) => {
              setUploadData(res);
              setChatHistoryIdState(res.chat_history_id);
              setPhase('questions');
              if (res.chat_history_id) {
                navigate(`/new-project/${res.chat_history_id}`, { replace: true });
              }
            }}
          />
        )}
        {phase === 'questions' && uploadData && (
          <QuestionsStep
            presalesId={uploadData.presales_id}
            initialQuestions={initialQuestions}
            questions={questions}
            setQuestions={setQuestions}
            answers={answers}
            setAnswers={setAnswers}
            additionalContext={additionalContext}
            setAdditionalContext={setAdditionalContext}
            onBack={() => setPhase('upload')}
            onComplete={() => setPhase('analysis')}
          />
        )}
        {phase === 'analysis' && uploadData && (
          <AnalysisStep
            presalesId={uploadData.presales_id}
            generating={generating}
            onBack={() => setPhase('questions')}
            onApplyAssumptions={handleApplyAssumptions}
            onGenerateReport={handleGenerateReport}
          />
        )}
        {phase === 'report' && reportContent && (
          <ReportStep
            reportContent={reportContent}
            projectTitle={projectTitle}
            chatHistoryId={chatHistoryIdState}
            onOpenChat={handleOpenChat}
            onBack={() => setPhase('analysis')}
            onContentChange={setReportContent}
          />
        )}
      </div>
    </div>
  );
}
