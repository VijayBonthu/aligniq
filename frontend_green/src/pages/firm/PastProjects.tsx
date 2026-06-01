import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  listPastProjects,
  deletePastProject,
  bulkUploadPastProjects,
  type PastProject,
} from '../../services/firmService';

export default function PastProjectsPage() {
  const [rows, setRows] = useState<PastProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try { setRows(await listPastProjects()); }
    catch { toast.error('Failed to load projects'); }
    finally { setLoading(false); }
  }

  useEffect(() => { refresh(); }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const res = await bulkUploadPastProjects(f);
      toast.success(`${res.inserted} inserted, ${res.failed} failed`);
      refresh();
    } catch { toast.error('Bulk upload failed'); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ''; }
  }

  async function handleDelete(p: PastProject) {
    if (!confirm(`Delete past project "${p.project_name}"? This also removes its embeddings.`)) return;
    try { await deletePastProject(p.project_id); refresh(); }
    catch { toast.error('Could not delete'); }
  }

  return (
    <div style={{ flex: 1, padding: '32px 40px', maxWidth: 1100, margin: '0 auto', width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 className="display" style={{ fontSize: 26, margin: '0 0 6px' }}>Past projects</h1>
          <p style={{ color: 'var(--fg-muted)', margin: 0 }}>
            Past deliveries the evidence agent retrieves during analysis (per-firm Chroma collection).
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} style={{ display: 'none' }} />
          <button className="btn btn-ghost" disabled={uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? 'Uploading…' : 'Bulk CSV upload'}
          </button>
          <Link className="btn btn-primary" to="/firm/past-projects/new">+ New project</Link>
        </div>
      </div>

      {loading ? (
        <div>Loading…</div>
      ) : rows.length === 0 ? (
        <p style={{ color: 'var(--fg-muted)' }}>No past projects yet. Add one to start grounding evidence in your portfolio.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)', color: 'var(--fg-dim)' }}>
              <th style={{ padding: '8px 6px' }}>Project</th>
              <th>Client</th>
              <th>Engagement</th>
              <th>Effort (est / actual)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map(p => (
              <tr key={p.project_id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '10px 6px' }}>
                  <Link to={`/firm/past-projects/${p.project_id}`} style={{ color: 'var(--accent)' }}>
                    {p.project_name}
                  </Link>
                </td>
                <td>{p.client_name || '—'}</td>
                <td>{p.engagement_type || '—'}</td>
                <td>
                  {p.effort_estimated_weeks ?? '—'} / {p.effort_actual_weeks ?? '—'} wks
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button className="btn btn-ghost" onClick={() => handleDelete(p)} style={{ padding: '4px 10px', fontSize: 12 }}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
