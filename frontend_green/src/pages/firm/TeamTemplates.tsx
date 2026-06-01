import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  listTeamTemplates,
  createTeamTemplate,
  updateTeamTemplate,
  deleteTeamTemplate,
  type TeamTemplate,
  type TeamTemplateRole,
} from '../../services/firmService';

const ENGAGEMENT_TYPES = ['', 'AI/ML', 'Web app', 'Data platform', 'Mobile', 'Other'];

function emptyRole(): TeamTemplateRole {
  return { role: '', seniority: 'Senior', count: 1, allocation_pct: 100 };
}

export default function TeamTemplatesPage() {
  const [templates, setTemplates] = useState<TeamTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<TeamTemplate | null>(null);
  const [form, setForm] = useState({
    template_name: '',
    engagement_type: '',
    notes: '',
    roles: [emptyRole()] as TeamTemplateRole[],
  });

  async function refresh() {
    try {
      setTemplates(await listTeamTemplates());
    } catch {
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  function startEdit(t: TeamTemplate) {
    setEditing(t);
    setForm({
      template_name: t.template_name,
      engagement_type: t.engagement_type || '',
      notes: t.notes || '',
      roles: t.roles?.length ? t.roles : [emptyRole()],
    });
  }

  function resetForm() {
    setEditing(null);
    setForm({ template_name: '', engagement_type: '', notes: '', roles: [emptyRole()] });
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form.template_name) {
      toast.error('Template name required');
      return;
    }
    const body = {
      template_name: form.template_name,
      engagement_type: form.engagement_type || null,
      notes: form.notes || null,
      roles: form.roles.filter(r => r.role),
      active: true,
    };
    try {
      if (editing) {
        await updateTeamTemplate(editing.template_id, body as Partial<TeamTemplate>);
        toast.success('Template updated');
      } else {
        await createTeamTemplate(body as Omit<TeamTemplate, 'template_id' | 'firm_id' | 'created_at' | 'updated_at'>);
        toast.success('Template added');
      }
      resetForm();
      refresh();
    } catch {
      toast.error('Could not save template');
    }
  }

  async function handleDelete(t: TeamTemplate) {
    if (!confirm(`Delete template "${t.template_name}"?`)) return;
    try {
      await deleteTeamTemplate(t.template_id);
      refresh();
    } catch {
      toast.error('Could not delete');
    }
  }

  function updateRole(idx: number, patch: Partial<TeamTemplateRole>) {
    setForm({ ...form, roles: form.roles.map((r, i) => i === idx ? { ...r, ...patch } : r) });
  }

  return (
    <div style={{ flex: 1, padding: '32px 40px', maxWidth: 960, margin: '0 auto', width: '100%' }}>
      <h1 className="display" style={{ fontSize: 26, margin: '0 0 24px' }}>Team templates</h1>

      <form onSubmit={handleSave} style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: 20, borderRadius: 8, marginBottom: 32 }}>
        <h3 style={{ marginTop: 0 }}>{editing ? 'Edit template' : 'New template'}</h3>

        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div className="field">
            <label>Template name</label>
            <input className="input" value={form.template_name} onChange={e => setForm({ ...form, template_name: e.target.value })} />
          </div>
          <div className="field">
            <label>Engagement type</label>
            <select className="input" value={form.engagement_type} onChange={e => setForm({ ...form, engagement_type: e.target.value })}>
              {ENGAGEMENT_TYPES.map(t => <option key={t} value={t}>{t || '— Any —'}</option>)}
            </select>
          </div>
        </div>

        <div className="field">
          <label>Notes</label>
          <textarea className="input" rows={2} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
        </div>

        <div style={{ marginTop: 12 }}>
          <label style={{ fontSize: 13, color: 'var(--fg-dim)' }}>Roles</label>
          {form.roles.map((r, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 80px 80px 32px', gap: 8, marginTop: 6 }}>
              <input className="input" placeholder="Role" value={r.role} onChange={e => updateRole(i, { role: e.target.value })} />
              <input className="input" placeholder="Seniority" value={r.seniority} onChange={e => updateRole(i, { seniority: e.target.value })} />
              <input className="input" type="number" min="1" placeholder="Count" value={r.count} onChange={e => updateRole(i, { count: parseInt(e.target.value) || 1 })} />
              <input className="input" type="number" min="0" max="100" placeholder="%" value={r.allocation_pct ?? ''} onChange={e => updateRole(i, { allocation_pct: parseInt(e.target.value) || undefined })} />
              <button type="button" className="btn btn-ghost" onClick={() => setForm({ ...form, roles: form.roles.filter((_, j) => j !== i) })} style={{ padding: '0 8px' }}>×</button>
            </div>
          ))}
          <button type="button" className="btn btn-ghost" onClick={() => setForm({ ...form, roles: [...form.roles, emptyRole()] })} style={{ marginTop: 8, fontSize: 12 }}>+ Add role</button>
        </div>

        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <button type="submit" className="btn btn-primary">{editing ? 'Update' : 'Create'}</button>
          {editing && <button type="button" className="btn btn-ghost" onClick={resetForm}>Cancel</button>}
        </div>
      </form>

      <h3>Existing templates</h3>
      {loading ? (
        <div>Loading…</div>
      ) : templates.length === 0 ? (
        <p style={{ color: 'var(--fg-muted)' }}>No templates yet.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {templates.map(t => (
            <div key={t.template_id} style={{ border: '1px solid var(--border)', padding: 16, borderRadius: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <strong>{t.template_name}</strong>
                  <span style={{ color: 'var(--fg-muted)', marginLeft: 8 }}>· {t.engagement_type || 'any'}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-ghost" onClick={() => startEdit(t)} style={{ padding: '4px 12px', fontSize: 12 }}>Edit</button>
                  <button className="btn btn-ghost" onClick={() => handleDelete(t)} style={{ padding: '4px 12px', fontSize: 12 }}>Delete</button>
                </div>
              </div>
              <div style={{ marginTop: 8, fontSize: 13, color: 'var(--fg-dim)' }}>
                {(t.roles || []).map((r, i) => (
                  <span key={i} style={{ marginRight: 12 }}>
                    {r.count}× {r.seniority} {r.role}{r.allocation_pct ? ` (${r.allocation_pct}%)` : ''}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
