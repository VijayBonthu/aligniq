import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  listRateCards,
  createRateCard,
  updateRateCard,
  deleteRateCard,
  type RateCard,
} from '../../services/firmService';

const SENIORITIES = ['Junior', 'Mid', 'Senior', 'Principal'];
const REGIONS = ['US', 'EU', 'APAC', 'LATAM', 'Remote'];

export default function RateCardPage() {
  const [rows, setRows] = useState<RateCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    role: '',
    seniority: 'Senior',
    region: 'US',
    hourly_rate_usd: 0,
  });

  async function refresh() {
    try {
      setRows(await listRateCards(false));
    } catch {
      toast.error('Failed to load rate card');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!form.role || form.hourly_rate_usd <= 0) {
      toast.error('Role and a positive hourly rate are required');
      return;
    }
    try {
      await createRateCard({ ...form, version: 1, active: true });
      setForm({ role: '', seniority: 'Senior', region: 'US', hourly_rate_usd: 0 });
      refresh();
      toast.success('Rate added');
    } catch {
      toast.error('Could not add rate');
    }
  }

  async function toggleActive(row: RateCard) {
    try {
      await updateRateCard(row.rate_id, { active: !row.active });
      refresh();
    } catch {
      toast.error('Could not update rate');
    }
  }

  async function handleDelete(row: RateCard) {
    if (!confirm(`Remove rate "${row.role} · ${row.seniority}"?`)) return;
    try {
      await deleteRateCard(row.rate_id);
      refresh();
    } catch {
      toast.error('Could not delete');
    }
  }

  return (
    <div style={{ flex: 1, padding: '32px 40px', maxWidth: 960, margin: '0 auto', width: '100%' }}>
      <h1 className="display" style={{ fontSize: 26, margin: '0 0 8px' }}>Rate card</h1>
      <p style={{ color: 'var(--fg-muted)', margin: '0 0 24px' }}>
        These rates power the <code>cost_breakdown</code> in every full report.
      </p>

      <form onSubmit={handleAdd} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 12, marginBottom: 24 }}>
        <input className="input" placeholder="Role (e.g. Backend Engineer)" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} />
        <select className="input" value={form.seniority} onChange={e => setForm({ ...form, seniority: e.target.value })}>
          {SENIORITIES.map(s => <option key={s}>{s}</option>)}
        </select>
        <select className="input" value={form.region} onChange={e => setForm({ ...form, region: e.target.value })}>
          {REGIONS.map(r => <option key={r}>{r}</option>)}
        </select>
        <input className="input" type="number" min="0" step="0.5" placeholder="$/hr" value={form.hourly_rate_usd || ''} onChange={e => setForm({ ...form, hourly_rate_usd: parseFloat(e.target.value) || 0 })} />
        <button type="submit" className="btn btn-primary">Add</button>
      </form>

      {loading ? (
        <div>Loading…</div>
      ) : rows.length === 0 ? (
        <p style={{ color: 'var(--fg-muted)' }}>No rates yet. Add your first row above.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)', color: 'var(--fg-dim)' }}>
              <th style={{ padding: '8px 6px' }}>Role</th>
              <th>Seniority</th>
              <th>Region</th>
              <th style={{ textAlign: 'right' }}>$/hr</th>
              <th>Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.rate_id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '10px 6px' }}>{r.role}</td>
                <td>{r.seniority}</td>
                <td>{r.region}</td>
                <td style={{ textAlign: 'right' }}>${r.hourly_rate_usd.toFixed(2)}</td>
                <td>
                  <label style={{ cursor: 'pointer' }}>
                    <input type="checkbox" checked={r.active} onChange={() => toggleActive(r)} />
                  </label>
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button className="btn btn-ghost" onClick={() => handleDelete(r)} style={{ padding: '4px 10px', fontSize: 12 }}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
