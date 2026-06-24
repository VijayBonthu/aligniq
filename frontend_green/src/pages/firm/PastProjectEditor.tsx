import { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  createPastProject,
  getPastProject,
  updatePastProject,
  type PastProject,
} from '../../services/firmService';

const ENGAGEMENT_TYPES = ['', 'AI/ML', 'Web app', 'Data platform', 'Mobile', 'Other'];

type FormState = Omit<PastProject, 'project_id' | 'firm_id' | 'created_at' | 'updated_at'>;

function emptyForm(): FormState {
  return {
    project_name: '',
    client_name: null,
    engagement_type: null,
    start_date: null,
    end_date: null,
    summary: null,
    original_brief_md: null,
    final_report_md: null,
    retrospective_md: null,
    effort_estimated_weeks: null,
    effort_actual_weeks: null,
  };
}

function strOrNull(v: string): string | null {
  return v.trim() ? v : null;
}

function numOrNull(v: string): number | null {
  if (!v.trim()) return null;
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}

export default function PastProjectEditor() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const isNew = !projectId || projectId === 'new';

  const [form, setForm] = useState<FormState>(emptyForm());
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isNew) return;
    getPastProject(projectId!)
      .then(p => {
        setForm({
          project_name: p.project_name,
          client_name: p.client_name,
          engagement_type: p.engagement_type,
          start_date: p.start_date,
          end_date: p.end_date,
          summary: p.summary,
          original_brief_md: p.original_brief_md,
          final_report_md: p.final_report_md,
          retrospective_md: p.retrospective_md,
          effort_estimated_weeks: p.effort_estimated_weeks,
          effort_actual_weeks: p.effort_actual_weeks,
        });
      })
      .catch(() => toast.error('Failed to load project'))
      .finally(() => setLoading(false));
  }, [projectId, isNew]);

  function patch<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(prev => ({ ...prev, [key]: value }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form.project_name.trim()) {
      toast.error('Project name is required');
      return;
    }
    setSaving(true);
    try {
      if (isNew) {
        const created = await createPastProject(form);
        toast.success('Project created — embeddings updating');
        navigate(`/firm/past-projects/${created.project_id}`);
      } else {
        await updatePastProject(projectId!, form);
        toast.success('Project saved — embeddings updating');
      }
    } catch {
      toast.error('Could not save');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div style={{ padding: 40 }}>Loading…</div>;

  return (
    <div style={{ flex: 1, padding: '32px 40px', maxWidth: 960, margin: '0 auto', width: '100%' }}>
      <div style={{ marginBottom: 16 }}>
        <Link to="/firm/past-projects" style={{ color: 'var(--accent)', fontSize: 13 }}>← Back to past projects</Link>
      </div>
      <h1 className="display" style={{ fontSize: 26, margin: '0 0 6px' }}>
        {isNew ? 'New past project' : 'Edit past project'}
      </h1>
      <p style={{ color: 'var(--fg-muted)', margin: '0 0 24px' }}>
        Saved content is chunked and embedded into your firm's evidence collection.
      </p>

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div className="field">
            <label>Project name *</label>
            <input
              className="input"
              value={form.project_name}
              onChange={e => patch('project_name', e.target.value)}
              placeholder="e.g. Acme data platform migration"
            />
          </div>
          <div className="field">
            <label>Client</label>
            <input
              className="input"
              value={form.client_name ?? ''}
              onChange={e => patch('client_name', strOrNull(e.target.value))}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <div className="field">
            <label>Engagement type</label>
            <select
              className="input"
              value={form.engagement_type ?? ''}
              onChange={e => patch('engagement_type', strOrNull(e.target.value))}
            >
              {ENGAGEMENT_TYPES.map(t => <option key={t} value={t}>{t || '— Any —'}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Start date</label>
            <input
              className="input"
              type="date"
              value={form.start_date ?? ''}
              onChange={e => patch('start_date', strOrNull(e.target.value))}
            />
          </div>
          <div className="field">
            <label>End date</label>
            <input
              className="input"
              type="date"
              value={form.end_date ?? ''}
              onChange={e => patch('end_date', strOrNull(e.target.value))}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="field">
            <label>Effort estimated (weeks)</label>
            <input
              className="input"
              type="number"
              min="0"
              step="0.5"
              value={form.effort_estimated_weeks ?? ''}
              onChange={e => patch('effort_estimated_weeks', numOrNull(e.target.value))}
            />
          </div>
          <div className="field">
            <label>Effort actual (weeks)</label>
            <input
              className="input"
              type="number"
              min="0"
              step="0.5"
              value={form.effort_actual_weeks ?? ''}
              onChange={e => patch('effort_actual_weeks', numOrNull(e.target.value))}
            />
          </div>
        </div>

        <div className="field">
          <label>Summary</label>
          <textarea
            className="input"
            rows={3}
            value={form.summary ?? ''}
            onChange={e => patch('summary', strOrNull(e.target.value))}
            placeholder="One-paragraph overview shown in retrieval previews."
          />
        </div>

        <div className="field">
          <label>Original brief (markdown)</label>
          <textarea
            className="input"
            rows={10}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}
            value={form.original_brief_md ?? ''}
            onChange={e => patch('original_brief_md', strOrNull(e.target.value))}
            placeholder="What the client asked for, scope, constraints…"
          />
        </div>

        <div className="field">
          <label>Final report (markdown)</label>
          <textarea
            className="input"
            rows={10}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}
            value={form.final_report_md ?? ''}
            onChange={e => patch('final_report_md', strOrNull(e.target.value))}
            placeholder="The deliverable: chosen stack, team, phases, costs…"
          />
        </div>

        <div className="field">
          <label>Retrospective (markdown)</label>
          <textarea
            className="input"
            rows={8}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}
            value={form.retrospective_md ?? ''}
            onChange={e => patch('retrospective_md', strOrNull(e.target.value))}
            placeholder="What worked, what bit us, what we'd change."
          />
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving…' : isNew ? 'Create' : 'Save changes'}
          </button>
          <Link to="/firm/past-projects" className="btn btn-ghost">Cancel</Link>
        </div>
      </form>
    </div>
  );
}
