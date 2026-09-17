import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, KeyRound } from 'lucide-react';
import { api, post } from '../api';

const SERVICES = [
  {key: 'seerr', label: 'Seerr', secretLabel: 'API key',
   description: 'Lets an admin request movies and TV shows through the request_movie_or_show MCP tool.'},
  {key: 'whisparr', label: 'Whisparr', secretLabel: 'API key',
   description: 'Lets an admin add adult scene/studio releases through the request_adult_scene MCP tool.'},
  {key: 'iptv_gtw', label: 'IPTV gateway', secretLabel: 'Export token',
   description: 'Registers its playlist and guide with Jellyfin when you use Connect IPTV gateway in Settings.'},
];

function Section({service, status, onSaved}) {
  const [url, setUrl] = useState(status?.url || ''), [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setBusy(true); setError(''); setSaved(false);
    try {
      await post(`/integrations/${service.key}`, {url, secret});
      setSaved(true); setSecret('');
      onSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <section className="mb-6 rounded-xl border border-white/10 bg-surface p-6">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-lg font-semibold">{service.label}</h2>
      {status?.configured && <span className="flex items-center gap-1.5 text-xs text-accent"><CheckCircle2 size={15}/>Configured</span>}
    </div>
    <p className="my-3 text-sm text-muted">{service.description}</p>
    <form className="space-y-4" onSubmit={submit}>
      <label className="block text-xs text-muted">URL
        <input className="field mt-2" required value={url} onChange={e => setUrl(e.target.value)} placeholder="http://service:port"/>
      </label>
      <label className="block text-xs text-muted">{service.secretLabel}
        <input className="field mt-2" type="password" required value={secret} onChange={e => setSecret(e.target.value)}
               placeholder={status?.configured ? 'Enter a new value to replace it' : ''}/>
      </label>
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
      {saved && <p role="status" className="text-xs text-accent">Saved and verified.</p>}
      <button className="btn-secondary" disabled={busy}>{busy ? 'Testing…' : 'Test & save'}</button>
    </form>
  </section>;
}

export default function SetupWizard() {
  const [status, setStatus] = useState(null), [error, setError] = useState('');
  function refresh() { api('/integrations/status').then(setStatus).catch(e => setError(e.message)); }
  useEffect(refresh, []);
  return <div className="mx-auto max-w-2xl px-6 pb-14 pt-32 md:px-10">
    <Link to="/settings" className="mb-6 flex items-center gap-2 text-xs text-muted"><ArrowLeft size={14}/>Back to settings</Link>
    <p className="eyebrow">Connect your tools</p>
    <h1 className="mb-3 mt-3 text-4xl font-bold">Integrations setup</h1>
    <p className="mb-8 flex items-center gap-1.5 text-sm text-muted">
      <KeyRound size={14} className="text-accent"/>Credentials are encrypted at rest and never stored as plain environment variables.
    </p>
    {error && <p role="alert" className="mb-5 rounded-lg bg-red-500/10 p-4 text-sm text-red-200">{error}</p>}
    {status && SERVICES.map(s => <Section key={s.key} service={s} status={status[s.key]} onSaved={refresh}/>)}
  </div>;
}
