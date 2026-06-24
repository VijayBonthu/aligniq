import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  listTechPreferences,
  createTechPreference,
  updateTechPreference,
  deleteTechPreference,
  type TechPreference,
} from '../../services/firmService';

const CATEGORIES = ['cloud', 'database', 'frontend', 'backend', 'auth', 'observability', 'ml/ai', 'other'];

function splitCsv(s: string): string[] {
  return s.split(',').map(x => x.trim()).filter(Boolean);
}

export default function TechPreferencesPage() {
  const [rows, setRows] = useState<TechPreference[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<TechPreference | null>(null);
  const [form, setForm] = useState({
    category: 'cloud',
    preferred: '',
    anti_preferred: '',
    rationale: '',
  });

  async function refresh() {
    try { setRows(await listTechPreferences()); }
    catch { toast.error('Failed to load preferences'); }
    finally { setLoading(false); }
  }

  useEffect(() => { refresh(); }, []);

  function startEdit(p: TechPreference) {
    setEditing(p);
    setForm({
      category: p.category,
      preferred: (p.preferred || []).join(', '),
      anti_preferred: (p.anti_preferred || []).join(', '),
      rationale: p.rationale || '',
    });
  }

  function resetForm() {
    setEditing(null);
    setForm({ category: 'cloud', preferred: '', anti_preferred: '', rationale: '' });
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      category: form.category,
      preferred: splitCsv(form.preferred),
      anti_preferred: splitCsv(form.anti_preferred),
      rationale: form.rationale || null,
    };
    try {
      if (editing) {
        await updateTechPreference(editing.pref_id, body as Partial<TechPreference>);
        toast.success('Preference updated');
      } else {
        await createTechPreference(body as Omit<TechPreference, 'pref_id' | 'firm_id' | 'created_at' | 'updated_at'>);
        toast.success('Preference added');
      }
      resetForm();
      refresh();
    } catch { toast.error('Could not save'); }
  }

  async function handleDelete(p: TechPreference) {
    if (!confirm(`Delete preferences for "${p.category}"?`)) return;
    try { await deleteTechPreference(p.pref_id); refresh(); }
    catch { toast.error('Could not delete'); }
  }

  return (
    <div style={{ flex: 1, padding: '32px 40px', maxWidth: 880, margin: '0 auto', width: '100%' }}>
      <h1 className="display" style={{ fontSize: 26, margin: '0 0 8px' }}>Tech preferences</h1>
      <p style={{ color: 'var(--fg-muted)', margin: '0 0 24px' }}>
        Anti-preferred items become risk flags when client requirements demand them.
      </p>

      <form onSubmit={handleSave} style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: 20, borderRadius: 8, marginBottom: 32 }}>
        <h3 style={{ marginTop: 0 }}>{editing ? 'Edit preference' : 'New preference'}</h3>

        <div className="field">
          <label>Category</label>
          <select className="input" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>

        <div className="field">
          <label>Preferred (comma-separated)</label>
          <input className="input" placeholder="AWS, Postgres, React" value={form.preferred} onChange={e => setForm({ ...form, preferred: e.target.value })} />
        </div>

        <div className="field">
          <label>Anti-preferred (comma-separated)</label>
          <input className="input" placeholder="Oracle, COBOL" value={form.anti_preferred} onChange={e => setForm({ ...form, anti_preferred: e.target.value })} />
        </div>

        <div className="field">
          <label>Rationale</label>
          <textarea className="input" rows={2} value={form.rationale} onChange={e => setForm({ ...form, rationale: e.target.value })} />
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" className="btn btn-primary">{editing ? 'Update' : 'Create'}</button>
          {editing && <button type="button" className="btn btn-ghost" onClick={resetForm}>Cancel</button>}
        </div>
      </form>

      <h3>Existing preferences</h3>
      {loading ? <div>Loading…</div> : rows.length === 0 ? <p style={{ color: 'var(--fg-muted)' }}>No preferences yet.</p> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {rows.map(p => (
            <div key={p.pref_id} style={{ border: '1px solid var(--border)', padding: 16, borderRadius: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong style={{ textTransform: 'capitalize' }}>{p.category}</strong>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-ghost" onClick={() => startEdit(p)} style={{ padding: '4px 12px', fontSize: 12 }}>Edit</button>
                  <button className="btn btn-ghost" onClick={() => handleDelete(p)} style={{ padding: '4px 12px', fontSize: 12 }}>Delete</button>
                </div>
              </div>
              <div style={{ marginTop: 8, fontSize: 13 }}>
                <div><span style={{ color: 'var(--ok)' }}>Prefer:</span> {(p.preferred || []).join(', ') || '—'}</div>
                <div><span style={{ color: 'var(--danger, #cc4444)' }}>Avoid:</span> {(p.anti_preferred || []).join(', ') || '—'}</div>
                {p.rationale && <div style={{ color: 'var(--fg-muted)', marginTop: 4 }}>{p.rationale}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
