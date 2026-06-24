import React from 'react';
import { Reveal } from './Reveal';
import { UploadScreen } from './screens/UploadScreen';
import { QuestionsScreen } from './screens/QuestionsScreen';
import { AnalysisScreen } from './screens/AnalysisScreen';
import { ReportScreen } from './screens/ReportScreen';
import { PipelineScreen } from './screens/PipelineScreen';

interface Bullet { h: string; t: string; }
interface FlowSectionProps {
  stepLabel: string;
  title: string;
  lede: string;
  bullets: Bullet[];
  reverse?: boolean;
  children: React.ReactNode;
}

const FlowSection: React.FC<FlowSectionProps> = ({ stepLabel, title, lede, bullets, reverse, children }) => (
  <section className="section flow-section">
    <div className="container">
      <div className="flow-split">
        <Reveal
          variant={reverse ? 'right' : 'left'}
          className="flow-copy"
          style={{ order: reverse ? 2 : 1 }}
        >
          <span className="eyebrow" style={{ color: 'var(--accent)' }}>{stepLabel}</span>
          <h2 className="display" style={{ fontSize: 34, letterSpacing: '-.02em', lineHeight: 1.06, margin: '10px 0 14px', color: 'var(--fg)' }}>
            {title}
          </h2>
          <p style={{ fontSize: 16, color: 'var(--fg-dim)', lineHeight: 1.55, marginBottom: 18 }}>
            {lede}
          </p>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 11 }}>
            {bullets.map((b, i) => (
              <li key={i} style={{ display: 'flex', gap: 11, fontSize: 13.5, color: 'var(--fg-dim)', lineHeight: 1.5 }}>
                <span className="mono" style={{ flexShrink: 0, color: 'var(--accent)', fontSize: 10, letterSpacing: '.08em', minWidth: 22, marginTop: 4 }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span><b style={{ color: 'var(--fg)' }}>{b.h}</b> — {b.t}</span>
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal
          variant="up"
          delay={90}
          className="flow-screen-wrap"
          style={{ order: reverse ? 1 : 2 }}
        >
          {children}
        </Reveal>
      </div>
    </div>
  </section>
);

/**
 * The real-flow tour: five faithful recreations of the actual product screens,
 * each beside the marketing copy for that step. Replaces the old abstract demo
 * + sample-report mockups with the real UI shapes, states, and stage names.
 */
export const RealFlowTour: React.FC = () => (
  <div id="how">
    <section className="section flow-intro">
      <div className="container" style={{ textAlign: 'center' }}>
        <Reveal>
          <div className="eyebrow section-eyebrow">How it works</div>
          <h2 className="display section-h" style={{ margin: '0 auto' }}>
            See a brief get <i>grounded</i> — step by step.
          </h2>
          <p className="section-sub" style={{ maxWidth: 640, margin: '14px auto 0' }}>
            Not a mockup. These are the real GroundedIQ screens — upload, interrogate, score, ship — each one running live.
          </p>
        </Reveal>
      </div>
    </section>

    <FlowSection
      stepLabel="STEP 01 · UPLOAD"
      title="Drop in the brief."
      lede="An RFP, a discovery deck, a Slack thread, a transcript — any fidelity. GroundedIQ runs five passes in under two minutes: extract, detect blind spots, identify P1 blockers, generate kickstart questions."
      bullets={[
        { h: 'PDF · DOCX · PPTX · TXT · MD · CSV', t: 'attach the brief in whatever shape it arrived in.' },
        { h: 'Five-pass analysis pipeline', t: 'each stage live on the upload screen.' },
        { h: 'No template gymnastics', t: 'no rewriting the brief into a form before you can scope.' },
      ]}
    >
      <UploadScreen />
    </FlowSection>

    <FlowSection
      reverse
      stepLabel="STEP 02 · QUESTIONS"
      title="Answer the P1 blockers. Defer the rest."
      lede="GroundedIQ separates the questions that must be answered from the ones that can wait. P1 blockers carry ‘why it matters’ — kickstart questions can be filled with proposed assumptions."
      bullets={[
        { h: 'P1 blockers', t: 'critical and must-answer before report generation.' },
        { h: 'Kickstart questions', t: 'leave blank and the analysis step proposes assumptions.' },
        { h: 'Free-form context box', t: 'paste call notes, Slack threads, anything the doc missed.' },
      ]}
    >
      <QuestionsScreen />
    </FlowSection>

    <FlowSection
      stepLabel="STEP 03 · ANALYSIS"
      title="A readiness score the client can read."
      lede="0–100, with contradictions detected, vague answers flagged, and a list of suggested assumptions you can apply with a click — or edit first, then apply."
      bullets={[
        { h: 'Readiness ring', t: '0–100 with three honest states: ready / ready-with-assumptions / needs-more-info.' },
        { h: 'Contradiction detection', t: 'cross-checked across every answer you wrote.' },
        { h: 'Apply assumptions in one click', t: 'tagged in the report so the client sees what was assumed.' },
      ]}
    >
      <AnalysisScreen />
    </FlowSection>

    <FlowSection
      reverse
      stepLabel="STEP 04 · REPORT"
      title="The consolidated requirements document."
      lede="A presales brief in minutes, with executive summary, P1 blockers, assumptions log, and proposed approach. Edit in-app. Export Markdown / PDF / DOCX. Send to the client."
      bullets={[
        { h: 'Edit in-app', t: 'no copy-paste-into-Notion ritual.' },
        { h: 'Assumptions log', t: 'every assumption captured with “impact if wrong”.' },
        { h: 'Versioned regenerations', t: 'iterate on answers, regenerate, keep version history.' },
      ]}
    >
      <ReportScreen />
    </FlowSection>

    <FlowSection
      stepLabel="OPTIONAL · FULL PIPELINE"
      title="The full BA report — when the engagement is signed."
      lede="Four stages: a planner sketches the report contract, a decision pass locks the typed tech / cost / timeline / team / verdict, every section is written in parallel, then a judge scores each one and sends weak sections back for a single revision."
      bullets={[
        { h: 'Plan → decide → write → judge', t: 'four streamed stages, live status on the page.' },
        { h: 'Sections written in parallel', t: 'the writers fan out, so it stays fast.' },
        { h: 'Background & resumable', t: 'leave mid-run and come back — the run keeps going.' },
      ]}
    >
      <PipelineScreen />
    </FlowSection>
  </div>
);
