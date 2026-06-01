import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { getMyFirm, updateMyFirm, type Firm } from '../../services/firmService';

export default function FirmSettings() {
  const [firm, setFirm] = useState<Firm | null>(null);
  const [name, setName] = useState('');
  const [logoUrl, setLogoUrl] = useState('');
  const [primaryColor, setPrimaryColor] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getMyFirm()
      .then(f => {
        setFirm(f);
        setName(f.name || '');
        setLogoUrl(f.logo_url || '');
        setPrimaryColor(f.primary_color || '');
      })
      .catch(() => toast.error('Failed to load firm'))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      const updated = await updateMyFirm({
        name: name || undefined,
        logo_url: logoUrl || undefined,
        primary_color: primaryColor || undefined,
      });
      setFirm(updated);
      toast.success('Firm updated');
    } catch {
      toast.error('Could not save');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div style={{ padding: 40 }}>Loading…</div>;
  if (!firm) return <div style={{ padding: 40 }}>Firm not found</div>;

  return (
    <div style={{ flex: 1, padding: '32px 40px', maxWidth: 640, margin: '0 auto', width: '100%' }}>
      <h1 className="display" style={{ fontSize: 26, margin: '0 0 24px' }}>Firm Settings</h1>

      <div className="field">
        <label>Firm name</label>
        <input className="input" value={name} onChange={e => setName(e.target.value)} />
      </div>

      <div className="field">
        <label>Logo URL</label>
        <input className="input" value={logoUrl} onChange={e => setLogoUrl(e.target.value)} placeholder="https://..." />
      </div>

      <div className="field">
        <label>Primary color (hex)</label>
        <input className="input" value={primaryColor} onChange={e => setPrimaryColor(e.target.value)} placeholder="#FF7A00" />
      </div>

      <button className="btn btn-primary" disabled={saving} onClick={handleSave}>
        {saving ? 'Saving…' : 'Save changes'}
      </button>

      <p style={{ marginTop: 32, color: 'var(--fg-muted)', fontSize: 13 }}>
        Firm ID: <code>{firm.firm_id}</code>
      </p>
    </div>
  );
}
