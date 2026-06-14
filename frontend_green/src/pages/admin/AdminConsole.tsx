import React, { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { useSiteConfig } from '../../context/SiteConfigContext';
import { useAuth } from '../../context/AuthContext';
import { friendlyError } from '../../services/api';
import * as ops from '../../services/adminOpsService';
import EmojiInsert from '../../components/ops/EmojiInsert';

type Tab = 'ops' | 'announcements' | 'changelog' | 'staff' | 'emails';

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em',
  color: 'var(--fg-muted)', marginBottom: 6, fontWeight: 600,
};
// A label row that pairs the field label with the emoji quick-insert button.
const labelRow: React.CSSProperties = { display: 'flex', alignItems: 'center', justifyContent: 'space-between' };
const fieldWrap: React.CSSProperties = { marginBottom: 16 };
const card: React.CSSProperties = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius)', padding: 20, marginBottom: 18,
};

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 14, marginBottom: 10 }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} style={{ width: 16, height: 16 }} />
      {label}
    </label>
  );
}

// ── Tab: Maintenance / read-only / feature flags ──
function OpsTab() {
  const { refresh } = useSiteConfig();
  const [state, setState] = useState<ops.OpsState | null>(null);
  const [saving, setSaving] = useState(false);
  const maintTitleRef = useRef<HTMLTextAreaElement>(null);
  const maintMsgRef = useRef<HTMLTextAreaElement>(null);
  const roMsgRef = useRef<HTMLInputElement>(null);
  // Raw text for the targeted-maintenance recipient list; parsed to an array on save.
  const [maintEmailsRaw, setMaintEmailsRaw] = useState('');

  useEffect(() => {
    ops.getSiteSettings().then((s) => {
      setState(s);
      setMaintEmailsRaw((s.maintenance.target_emails || []).join('\n'));
    }).catch((e) => toast.error(friendlyError(e)));
  }, []);
  if (!state) return <p style={{ color: 'var(--fg-dim)' }}>Loading…</p>;

  const m = state.maintenance, ro = state.read_only, ff = state.feature_flags;
  const set = (optimistic: Partial<ops.OpsState>) =>
    setState({ ...state, ...optimistic } as ops.OpsState);

  const save = async () => {
    setSaving(true);
    try {
      const next = await ops.putSiteSettings({
        maintenance: {
          on: m.on, title: m.title, message: m.message, eta: m.eta, media_url: m.media_url,
          allowlist_ips: m.allowlist_ips, target_emails: parseEmails(maintEmailsRaw),
        },
        read_only: { on: ro.on, message: ro.message },
        feature_flags: ff,
      });
      setState(next);
      refresh(); // flip the live gate/banner immediately
      toast.success('Saved — live now.');
    } catch (e) { toast.error(friendlyError(e)); }
    finally { setSaving(false); }
  };

  // One-click "we're back to normal": turn maintenance off AND clear any targeting.
  const endMaintenance = async () => {
    setSaving(true);
    try {
      const next = await ops.putSiteSettings({ maintenance: { on: false, target_emails: [] } });
      setState(next);
      setMaintEmailsRaw('');
      refresh();
      toast.success('Maintenance ended — back to normal.');
    } catch (e) { toast.error(friendlyError(e)); }
    finally { setSaving(false); }
  };

  const targetCount = parseEmails(maintEmailsRaw).length;

  return (
    <div>
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 16 }}>🛑 Maintenance mode</h3>
        <Toggle checked={m.on} label="Maintenance is ON (staff always bypass)"
                onChange={(v) => set({maintenance: { ...m, on: v } })} />
        {m.on && (
          <p style={{ fontSize: 12.5, margin: '0 0 12px', lineHeight: 1.5,
                      color: targetCount ? 'var(--accent)' : 'var(--warn, #c89e6e)' }}>
            {targetCount
              ? `🎯 Targeted: only the ${targetCount} listed account${targetCount > 1 ? 's' : ''} below will see the maintenance page — everyone else (and anonymous visitors) uses the site normally.`
              : '⚠️ Site-wide: every visitor — logged in or not — is blocked until you turn this off.'}
          </p>
        )}
        <div style={fieldWrap}>
          <div style={labelRow}>
            <label style={labelStyle}>Title (Enter for a new line)</label>
            <EmojiInsert targetRef={maintTitleRef} value={m.title} onChange={(v) => set({ maintenance: { ...m, title: v } })} />
          </div>
          <textarea ref={maintTitleRef} className="input" rows={2} value={m.title} placeholder="We'll be right back"
                    onChange={(e) => set({maintenance: { ...m, title: e.target.value } })} />
        </div>
        <div style={fieldWrap}>
          <div style={labelRow}>
            <label style={labelStyle}>Message</label>
            <EmojiInsert targetRef={maintMsgRef} value={m.message} onChange={(v) => set({ maintenance: { ...m, message: v } })} />
          </div>
          <textarea ref={maintMsgRef} className="input" rows={3} value={m.message} placeholder="GroundedIQ is down for brief maintenance…"
                    onChange={(e) => set({maintenance: { ...m, message: e.target.value } })} />
        </div>
        <div style={fieldWrap}>
          <label style={labelStyle}>ETA (free text)</label>
          <input className="input" value={m.eta} placeholder="approx. 14:30 UTC"
                 onChange={(e) => set({maintenance: { ...m, eta: e.target.value } })} />
        </div>
        <div style={fieldWrap}>
          <label style={labelStyle}>GIF / image URL (optional)</label>
          <input className="input" value={m.media_url || ''} placeholder="https://media.giphy.com/…/giphy.gif"
                 onChange={(e) => set({maintenance: { ...m, media_url: e.target.value } })} />
          <p style={{ color: 'var(--fg-dim)', fontSize: 12, margin: '6px 0 0' }}>
            Shown on the maintenance page (capped in size). Paste a direct link to a .gif/.png/.jpg.
          </p>
        </div>
        <div style={fieldWrap}>
          <label style={labelStyle}>Bypass IP allowlist (comma-separated)</label>
          <input className="input" value={(m.allowlist_ips || []).join(', ')} placeholder="203.0.113.4, 198.51.100.7"
                 onChange={(e) => set({maintenance: { ...m, allowlist_ips: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } })} />
        </div>
        <div style={fieldWrap}>
          <label style={labelStyle}>Show only to these emails (optional — targeted)</label>
          <textarea className="input" rows={2} value={maintEmailsRaw}
                    placeholder={'alice@acme.com, bob@acme.com\n(leave blank for normal site-wide maintenance)'}
                    onChange={(e) => setMaintEmailsRaw(e.target.value)} />
          <p style={{ color: 'var(--fg-dim)', fontSize: 12, margin: '6px 0 0' }}>
            Requires <strong>Maintenance is ON</strong> above. When filled, <strong>only</strong> these
            accounts see the maintenance page (after they sign in); everyone else — including anonymous
            visitors — uses the site normally. Leave blank to take the whole site down. Staff always bypass.
          </p>
        </div>
        {m.on && (
          <button className="btn btn-ghost" disabled={saving} onClick={endMaintenance}
                  style={{ color: 'var(--danger)', padding: '6px 12px' }}>
            End maintenance — revert to normal
          </button>
        )}
      </div>

      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 16 }}>📖 Read-only mode</h3>
        <Toggle checked={ro.on} label="Read-only (users can view but not make changes)"
                onChange={(v) => set({read_only: { ...ro, on: v } })} />
        <div style={fieldWrap}>
          <div style={labelRow}>
            <label style={labelStyle}>Message</label>
            <EmojiInsert targetRef={roMsgRef} value={ro.message} onChange={(v) => set({ read_only: { ...ro, message: v } })} />
          </div>
          <input ref={roMsgRef} className="input" value={ro.message} placeholder="We're in read-only mode for brief maintenance."
                 onChange={(e) => set({read_only: { ...ro, message: e.target.value } })} />
        </div>
      </div>

      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 16 }}>🔧 Feature kill switches</h3>
        <Toggle checked={ff.signups_enabled} label="Sign-ups enabled"
                onChange={(v) => set({feature_flags: { ...ff, signups_enabled: v } })} />
        <Toggle checked={ff.logins_enabled} label="Logins enabled"
                onChange={(v) => set({feature_flags: { ...ff, logins_enabled: v } })} />
        <Toggle checked={ff.pipeline_enabled} label="Report pipeline enabled (turn off to pause generation, e.g. LLM outage / cost spike)"
                onChange={(v) => set({feature_flags: { ...ff, pipeline_enabled: v } })} />
      </div>

      <button className="btn btn-primary btn-lg" disabled={saving} onClick={save}>
        {saving ? 'Saving…' : 'Save — apply live'}
      </button>
    </div>
  );
}

// ── Tab: Announcements ──
const BLANK_ANN: ops.AnnouncementInput = {
  kind: 'info', title: '', body: '', active: true, audience: 'all', dismissible: true,
  link_url: '', link_label: '', target_emails: [],
};

// Parse a free-text recipient list (comma / newline / space separated) into a clean
// lowercased, de-duped array. The backend normalizes again; this is just for UX.
const parseEmails = (raw: string): string[] =>
  Array.from(new Set(raw.split(/[\s,;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean)));

function AnnouncementsTab() {
  const { refresh } = useSiteConfig();
  const [list, setList] = useState<ops.AdminAnnouncement[]>([]);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<ops.AnnouncementInput>(BLANK_ANN);
  // Raw text for the recipient field, kept separate so the textarea doesn't fight the
  // user's cursor while typing; parsed to an array on submit.
  const [emailsRaw, setEmailsRaw] = useState('');
  const titleRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const load = () => ops.listAnnouncements().then(setList).catch((e) => toast.error(friendlyError(e)));
  useEffect(() => { load(); }, []);

  const startEdit = (a: ops.AdminAnnouncement) => {
    setEditId(a.id);
    setForm({ kind: a.kind, title: a.title, body: a.body || '', active: a.active, audience: a.audience,
              dismissible: a.dismissible, link_url: a.link_url || '', link_label: a.link_label || '' });
    setEmailsRaw((a.target_emails || []).join('\n'));
  };
  const reset = () => { setEditId(null); setForm(BLANK_ANN); setEmailsRaw(''); };

  const submit = async () => {
    if (!form.title.trim()) return toast.error('Title is required.');
    const targeted = form.audience === 'users';
    const target_emails = targeted ? parseEmails(emailsRaw) : [];
    if (targeted && target_emails.length === 0) return toast.error('Add at least one recipient email.');
    const payload = { ...form, target_emails };
    try {
      if (editId) await ops.updateAnnouncement(editId, payload);
      else await ops.createAnnouncement(payload);
      toast.success(editId ? 'Updated.' : 'Published.');
      reset(); await load(); refresh();
    } catch (e) { toast.error(friendlyError(e)); }
  };
  const remove = async (id: string) => {
    try { await ops.deleteAnnouncement(id); await load(); refresh(); } catch (e) { toast.error(friendlyError(e)); }
  };
  const toggleActive = async (a: ops.AdminAnnouncement) => {
    try { await ops.updateAnnouncement(a.id, { active: !a.active }); await load(); refresh(); } catch (e) { toast.error(friendlyError(e)); }
  };

  return (
    <div>
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 16 }}>{editId ? 'Edit announcement' : 'New announcement'}</h3>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ ...fieldWrap, flex: '0 0 160px' }}>
            <label style={labelStyle}>Kind</label>
            <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {['info', 'success', 'warning', 'outage', 'maintenance'].map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div style={{ ...fieldWrap, flex: '0 0 160px' }}>
            <label style={labelStyle}>Audience</label>
            <select className="input" value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })}>
              <option value="all">Everyone</option>
              <option value="authenticated">Signed-in only</option>
              <option value="users">Specific people (by email)</option>
            </select>
          </div>
        </div>
        {form.audience === 'users' && (
          <div style={fieldWrap}>
            <label style={labelStyle}>Recipient emails</label>
            <textarea className="input" rows={3} value={emailsRaw}
                      placeholder={'alice@acme.com, bob@acme.com\nor one per line'}
                      onChange={(e) => setEmailsRaw(e.target.value)} />
            <p style={{ color: 'var(--fg-dim)', fontSize: 12, margin: '6px 0 0' }}>
              Only signed-in accounts matching these emails see it. Comma or newline separated; unknown
              emails are simply ignored. (Recipient list is never exposed to other users.)
            </p>
          </div>
        )}
        <div style={fieldWrap}>
          <div style={labelRow}>
            <label style={labelStyle}>Title</label>
            <EmojiInsert targetRef={titleRef} value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
          </div>
          <input ref={titleRef} className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div style={fieldWrap}>
          <div style={labelRow}>
            <label style={labelStyle}>Body (optional)</label>
            <EmojiInsert targetRef={bodyRef} value={form.body || ''} onChange={(v) => setForm({ ...form, body: v })} />
          </div>
          <textarea ref={bodyRef} className="input" rows={2} value={form.body || ''} onChange={(e) => setForm({ ...form, body: e.target.value })} />
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ ...fieldWrap, flex: 1 }}>
            <label style={labelStyle}>Link URL (optional)</label>
            <input className="input" value={form.link_url || ''} onChange={(e) => setForm({ ...form, link_url: e.target.value })} />
          </div>
          <div style={{ ...fieldWrap, flex: 1 }}>
            <label style={labelStyle}>Link label</label>
            <input className="input" value={form.link_label || ''} onChange={(e) => setForm({ ...form, link_label: e.target.value })} />
          </div>
        </div>
        <Toggle checked={!!form.active} label="Active" onChange={(v) => setForm({ ...form, active: v })} />
        <Toggle checked={!!form.dismissible} label="Dismissible by users" onChange={(v) => setForm({ ...form, dismissible: v })} />
        <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
          <button className="btn btn-primary" onClick={submit}>{editId ? 'Update' : 'Publish'}</button>
          {editId && <button className="btn btn-ghost" onClick={reset}>Cancel</button>}
        </div>
      </div>

      <h3 style={{ fontSize: 15, margin: '24px 0 12px' }}>All announcements</h3>
      {list.length === 0 && <p style={{ color: 'var(--fg-dim)', fontSize: 14 }}>None yet.</p>}
      {list.map((a) => (
        <div key={a.id} style={{ ...card, display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px' }}>
          <span style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--fg-muted)', width: 76 }}>{a.kind}</span>
          <span style={{ flex: 1 }}>{a.title}{!a.active && <em style={{ color: 'var(--fg-muted)' }}> (inactive)</em>}</span>
          <button className="btn btn-ghost" style={{ padding: '4px 10px' }} onClick={() => toggleActive(a)}>{a.active ? 'Deactivate' : 'Activate'}</button>
          <button className="btn btn-ghost" style={{ padding: '4px 10px' }} onClick={() => startEdit(a)}>Edit</button>
          <button className="btn btn-ghost" style={{ padding: '4px 10px', color: 'var(--danger)' }} onClick={() => remove(a.id)}>Delete</button>
        </div>
      ))}
    </div>
  );
}

// ── Tab: Changelog ──
const BLANK_CL: ops.ChangelogInput = { version: '', title: '', body: '', category: 'feature', media_url: '', published: false };

function ChangelogTab() {
  const { refresh } = useSiteConfig();
  const [list, setList] = useState<ops.AdminChangelogEntry[]>([]);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<ops.ChangelogInput>(BLANK_CL);
  const titleRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const load = () => ops.listChangelogAdmin().then(setList).catch((e) => toast.error(friendlyError(e)));
  useEffect(() => { load(); }, []);

  const startEdit = (c: ops.AdminChangelogEntry) => {
    setEditId(c.id);
    setForm({ version: c.version || '', title: c.title, body: c.body || '', category: c.category || 'feature', media_url: c.media_url || '', published: c.published });
  };
  const reset = () => { setEditId(null); setForm(BLANK_CL); };

  const submit = async () => {
    if (!form.title.trim()) return toast.error('Title is required.');
    try {
      if (editId) await ops.updateChangelog(editId, form);
      else await ops.createChangelog(form);
      toast.success(editId ? 'Updated.' : 'Saved.');
      reset(); await load(); refresh();
    } catch (e) { toast.error(friendlyError(e)); }
  };
  const remove = async (id: string) => {
    try { await ops.deleteChangelog(id); await load(); refresh(); } catch (e) { toast.error(friendlyError(e)); }
  };
  const togglePublish = async (c: ops.AdminChangelogEntry) => {
    try { await ops.updateChangelog(c.id, { published: !c.published }); await load(); refresh(); } catch (e) { toast.error(friendlyError(e)); }
  };

  return (
    <div>
      <div style={card}>
        <h3 style={{ margin: '0 0 14px', fontSize: 16 }}>{editId ? 'Edit entry' : 'New changelog entry'}</h3>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ ...fieldWrap, flex: '0 0 140px' }}>
            <label style={labelStyle}>Version</label>
            <input className="input" value={form.version || ''} placeholder="v1.4" onChange={(e) => setForm({ ...form, version: e.target.value })} />
          </div>
          <div style={{ ...fieldWrap, flex: '0 0 160px' }}>
            <label style={labelStyle}>Category</label>
            <select className="input" value={form.category || 'feature'} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {['feature', 'improvement', 'fix'].map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
        </div>
        <div style={fieldWrap}>
          <div style={labelRow}>
            <label style={labelStyle}>Title</label>
            <EmojiInsert targetRef={titleRef} value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
          </div>
          <input ref={titleRef} className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div style={fieldWrap}>
          <div style={labelRow}>
            <label style={labelStyle}>Body</label>
            <EmojiInsert targetRef={bodyRef} value={form.body || ''} onChange={(v) => setForm({ ...form, body: v })} />
          </div>
          <textarea ref={bodyRef} className="input" rows={3} value={form.body || ''} onChange={(e) => setForm({ ...form, body: e.target.value })} />
        </div>
        <div style={fieldWrap}>
          <label style={labelStyle}>GIF / image URL (optional)</label>
          <input className="input" value={form.media_url || ''} placeholder="https://media.giphy.com/…/giphy.gif"
                 onChange={(e) => setForm({ ...form, media_url: e.target.value })} />
          <p style={{ color: 'var(--fg-dim)', fontSize: 12, margin: '6px 0 0' }}>
            Shown in "What's new" (capped in size). Paste a direct link to a .gif/.png/.jpg.
          </p>
        </div>
        <Toggle checked={!!form.published} label="Published (visible in What's new)" onChange={(v) => setForm({ ...form, published: v })} />
        <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
          <button className="btn btn-primary" onClick={submit}>{editId ? 'Update' : 'Save'}</button>
          {editId && <button className="btn btn-ghost" onClick={reset}>Cancel</button>}
        </div>
      </div>

      <h3 style={{ fontSize: 15, margin: '24px 0 12px' }}>All entries</h3>
      {list.length === 0 && <p style={{ color: 'var(--fg-dim)', fontSize: 14 }}>None yet.</p>}
      {list.map((c) => (
        <div key={c.id} style={{ ...card, display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-muted)', width: 60 }}>{c.version || '—'}</span>
          <span style={{ flex: 1 }}>{c.title}{!c.published && <em style={{ color: 'var(--fg-muted)' }}> (draft)</em>}</span>
          <button className="btn btn-ghost" style={{ padding: '4px 10px' }} onClick={() => togglePublish(c)}>{c.published ? 'Unpublish' : 'Publish'}</button>
          <button className="btn btn-ghost" style={{ padding: '4px 10px' }} onClick={() => startEdit(c)}>Edit</button>
          <button className="btn btn-ghost" style={{ padding: '4px 10px', color: 'var(--danger)' }} onClick={() => remove(c.id)}>Delete</button>
        </div>
      ))}
    </div>
  );
}

// ── Tab: Staff access (admins manage admins) ──
function StaffTab() {
  const { user } = useAuth();
  const [list, setList] = useState<ops.StaffUser[]>([]);
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => ops.listStaff().then(setList).catch((e) => toast.error(friendlyError(e)));
  useEffect(() => { load(); }, []);

  const grant = async () => {
    if (!email.trim()) return toast.error('Enter an email.');
    setBusy(true);
    try { await ops.setStaff(email.trim(), true); toast.success('Staff access granted.'); setEmail(''); await load(); }
    catch (e) { toast.error(friendlyError(e)); }
    finally { setBusy(false); }
  };
  const revoke = async (em: string) => {
    try { await ops.setStaff(em, false); toast.success('Access revoked.'); await load(); }
    catch (e) { toast.error(friendlyError(e)); }
  };

  return (
    <div>
      <div style={card}>
        <h3 style={{ margin: '0 0 6px', fontSize: 16 }}>Grant staff access</h3>
        <p style={{ color: 'var(--fg-dim)', fontSize: 13, margin: '0 0 14px' }}>
          The person must have signed up first. Staff can manage maintenance, announcements, changelog, and access.
        </p>
        <div style={{ display: 'flex', gap: 10 }}>
          <input className="input" style={{ flex: 1 }} type="email" placeholder="teammate@grounded-iq.com"
                 value={email} onChange={(e) => setEmail(e.target.value)} />
          <button className="btn btn-primary" disabled={busy} onClick={grant}>Grant access</button>
        </div>
      </div>

      <h3 style={{ fontSize: 15, margin: '24px 0 12px' }}>Current staff ({list.length})</h3>
      {list.length === 0 && <p style={{ color: 'var(--fg-dim)', fontSize: 14 }}>None yet.</p>}
      {list.map((s) => {
        const isSelf = (user?.email || '').toLowerCase() === s.email.toLowerCase();
        return (
          <div key={s.user_id} style={{ ...card, display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px' }}>
            <span style={{ flex: 1 }}>
              {s.full_name ? `${s.full_name} · ` : ''}{s.email}
              {isSelf && <em style={{ color: 'var(--fg-muted)' }}> (you)</em>}
            </span>
            {!isSelf && (
              <button className="btn btn-ghost" style={{ padding: '4px 10px', color: 'var(--danger)' }} onClick={() => revoke(s.email)}>Revoke</button>
            )}
          </div>
        );
      })}
    </div>
  );
}

const TAB_LABELS: Record<Tab, string> = {
  ops: 'Maintenance & switches',
  announcements: 'Announcements',
  changelog: 'Changelog',
  staff: 'Staff access',
  emails: 'Client emails',
};

const EMAIL_TEMPLATE_KEYS: { key: string; label: string }[] = [
  { key: 'questionnaire_invite', label: 'Questionnaire invite' },
  { key: 'questionnaire_reminder', label: 'Questionnaire reminder' },
];
const EMAIL_FIELDS: { key: keyof ops.EmailTemplateFields; label: string; multiline?: boolean }[] = [
  { key: 'subject', label: 'Subject' },
  { key: 'heading', label: 'Heading' },
  { key: 'intro', label: 'Intro paragraph', multiline: true },
  { key: 'button_label', label: 'Button label' },
  { key: 'signoff', label: 'Sign-off (optional)', multiline: true },
];

function EmailTemplatesTab() {
  const [search, setSearch] = useState('');
  const [firms, setFirms] = useState<ops.FirmRef[]>([]);
  const [selected, setSelected] = useState<ops.FirmRef | null>(null);
  const [data, setData] = useState<ops.FirmEmailTemplates | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ops.EmailTemplateFields>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => { ops.listFirms(search).then(setFirms).catch((e) => toast.error(friendlyError(e))); }, 250);
    return () => clearTimeout(t);
  }, [search]);

  const selectFirm = async (f: ops.FirmRef) => {
    setSelected(f);
    setData(null);
    try {
      const res = await ops.getFirmEmailTemplates(f.firm_id);
      setData(res);
      const d: Record<string, ops.EmailTemplateFields> = {};
      for (const { key } of EMAIL_TEMPLATE_KEYS) d[key] = { ...(res.templates[key]?.override || {}) };
      setDrafts(d);
    } catch (e) { toast.error(friendlyError(e)); }
  };

  const setField = (tkey: string, fkey: keyof ops.EmailTemplateFields, v: string) =>
    setDrafts((p) => ({ ...p, [tkey]: { ...p[tkey], [fkey]: v } }));

  const save = async (tkey: string) => {
    if (!selected) return;
    setSavingKey(tkey);
    try {
      await ops.saveFirmEmailTemplate(selected.firm_id, tkey, drafts[tkey] || {});
      toast.success('Template saved — this org now uses your custom copy.');
    } catch (e) { toast.error(friendlyError(e)); }
    finally { setSavingKey(null); }
  };

  return (
    <div>
      <div style={card}>
        <h3 style={{ margin: '0 0 6px', fontSize: 16 }}>Client email templates</h3>
        <p style={{ color: 'var(--fg-dim)', fontSize: 13, margin: '0 0 14px' }}>
          Customize the questionnaire emails per organization. Leave a field blank to use the GroundedIQ default.
          The GroundedIQ brand and the email layout are always applied — you're only editing the copy.
        </p>
        <input className="input" style={{ width: '100%' }} placeholder="Search organizations…"
               value={search} onChange={(e) => setSearch(e.target.value)} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
          {firms.map((f) => (
            <button key={f.firm_id} className="btn btn-ghost" onClick={() => selectFirm(f)}
                    style={{ padding: '4px 10px', fontSize: 13, border: `1px solid ${selected?.firm_id === f.firm_id ? 'var(--accent)' : 'var(--border)'}`, color: selected?.firm_id === f.firm_id ? 'var(--accent)' : 'var(--fg-dim)' }}>
              {f.name}
            </button>
          ))}
          {firms.length === 0 && <span style={{ color: 'var(--fg-muted)', fontSize: 13 }}>No organizations match.</span>}
        </div>
      </div>

      {selected && data && EMAIL_TEMPLATE_KEYS.map(({ key, label }) => {
        const defaults = data.templates[key]?.defaults || {};
        return (
          <div key={key} style={{ ...card, marginTop: 16 }}>
            <h4 style={{ margin: '0 0 10px', fontSize: 15 }}>{label} — <span style={{ color: 'var(--fg-muted)', fontWeight: 400 }}>{selected.name}</span></h4>
            {EMAIL_FIELDS.map(({ key: fkey, label: flabel, multiline }) => (
              <div key={fkey} style={{ marginBottom: 10 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--fg-muted)', marginBottom: 4 }}>{flabel}</label>
                {multiline ? (
                  <textarea className="input" style={{ width: '100%', minHeight: 56 }}
                            placeholder={(defaults as Record<string, string>)[fkey] || ''}
                            value={(drafts[key]?.[fkey] as string) || ''}
                            onChange={(e) => setField(key, fkey, e.target.value)} />
                ) : (
                  <input className="input" style={{ width: '100%' }}
                         placeholder={(defaults as Record<string, string>)[fkey] || ''}
                         value={(drafts[key]?.[fkey] as string) || ''}
                         onChange={(e) => setField(key, fkey, e.target.value)} />
                )}
              </div>
            ))}
            <p style={{ fontSize: 11, color: 'var(--fg-muted)', margin: '4px 0 10px' }}>
              Tip: use <code>{'{firm}'}</code> in the heading or intro to insert the firm's name.
            </p>
            <button className="btn btn-primary" disabled={savingKey === key} onClick={() => save(key)}>
              {savingKey === key ? 'Saving…' : `Save ${label.toLowerCase()}`}
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default function AdminConsole() {
  const [tab, setTab] = useState<Tab>('ops');
  return (
    <div style={{ padding: '32px 40px', maxWidth: 880, width: '100%', margin: '0 auto' }}>
      <h1 className="display" style={{ fontSize: 30, margin: '0 0 4px' }}>Operations console</h1>
      <p style={{ color: 'var(--fg-dim)', fontSize: 14, margin: '0 0 24px' }}>
        Platform staff controls — every change applies live, no deploy or restart.
      </p>
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => {
          const active = tab === t;
          return (
            <button key={t} onClick={() => setTab(t)} style={{
              border: 'none', background: 'transparent', padding: '8px 14px', fontSize: 13, cursor: 'pointer',
              color: active ? 'var(--accent)' : 'var(--fg-muted)',
              borderBottom: `2px solid ${active ? 'var(--accent)' : 'transparent'}`, marginBottom: -1,
              fontWeight: active ? 600 : 400,
            }}>{TAB_LABELS[t]}</button>
          );
        })}
      </div>
      {tab === 'ops' && <OpsTab />}
      {tab === 'announcements' && <AnnouncementsTab />}
      {tab === 'changelog' && <ChangelogTab />}
      {tab === 'staff' && <StaffTab />}
      {tab === 'emails' && <EmailTemplatesTab />}
    </div>
  );
}
