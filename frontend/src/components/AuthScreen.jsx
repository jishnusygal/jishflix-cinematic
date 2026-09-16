import { useEffect, useState } from 'react';
import { Clapperboard, ArrowRight, ShieldCheck } from 'lucide-react';
import { post } from '../api';
export default function AuthScreen({onLogin}) {
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [quick, setQuick] = useState(null);
  useEffect(() => {
    if (!quick) return;
    let alive = true, timeout;
    const poll = async () => {
      try { const result = await post('/auth/quick-connect/poll', {secret: quick.Secret}); if (alive && result.user) {onLogin(result.user); return;} }
      catch (e) {if (alive) {setError(e.message); setQuick(null);} return;}
      if (alive) timeout = setTimeout(poll, 3000);
    };
    timeout = setTimeout(poll, 3000);
    return () => {alive = false; clearTimeout(timeout);};
  }, [quick, onLogin]);
  async function login(event) {
    event.preventDefault(); setError(''); setBusy(true);
    const data = new FormData(event.currentTarget);
    try {onLogin(await post('/auth/login', {username: data.get('username'), password: data.get('password')}));}
    catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  async function pair() {setError(''); setBusy(true); try {setQuick(await post('/auth/quick-connect'));} catch (e) {setError(e.message);} finally {setBusy(false);}}
  return <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-16"><div className="absolute inset-0 bg-[radial-gradient(ellipse_at_20%_10%,#15343b_0%,transparent_50%)]"/><div className="relative grid w-full max-w-5xl gap-16 lg:grid-cols-2 lg:items-center"><section><div className="mb-16 flex items-center gap-3"><Clapperboard className="text-accent" size={32}/><span className="text-xl font-bold tracking-tight">jishflix<span className="ml-2 text-[9px] font-medium uppercase tracking-[.25em] text-muted">cinematic</span></span></div><p className="eyebrow">The best seat is yours</p><h1 className="mt-5 text-5xl font-bold leading-[1.1] tracking-tight md:text-6xl">A whole world.<br/>All in your library.</h1><p className="mt-6 max-w-sm text-sm leading-7 text-muted">The films you love. The shows you stay up for. Your music, your live channels. One beautifully personal place.</p><div className="mt-10 flex items-center gap-2 text-xs text-slate-400"><ShieldCheck size={16} className="text-accent"/>Self-hosted. Powered by your Jellyfin server.</div></section><section className="glass rounded-2xl p-7 md:p-10"><h2 className="text-2xl font-semibold">Welcome home.</h2><p className="mb-8 mt-2 text-sm text-muted">Sign in with your Jellyfin account.</p>{error && <p role="alert" className="mb-5 rounded-lg border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-200">{error}</p>}{quick ? <div className="text-center"><p className="text-sm text-muted">On a signed-in Jellyfin device, open Quick Connect and enter:</p><p className="my-8 text-4xl font-bold tracking-[.3em] text-accent">{quick.Code}</p><p role="status" className="text-xs text-muted">Waiting for approval…</p><button className="btn-secondary mt-7 w-full" onClick={() => setQuick(null)}>Back to sign in</button></div> : <><form onSubmit={login} className="space-y-5"><label className="block text-xs font-medium">Username<input className="field mt-2" name="username" autoComplete="username" required placeholder="Your Jellyfin username"/></label><label className="block text-xs font-medium">Password<input className="field mt-2" type="password" name="password" autoComplete="current-password" placeholder="Your password"/></label><button className="btn-primary w-full" disabled={busy}>{busy ? 'Signing in…' : 'Enter your cinema'}<ArrowRight size={16}/></button></form><div className="my-6 flex items-center gap-4 text-[10px] uppercase tracking-widest text-slate-500"><span className="h-px flex-1 bg-white/10"/>or<span className="h-px flex-1 bg-white/10"/></div><button className="btn-secondary w-full" disabled={busy} onClick={pair}>Pair with Quick Connect</button></>}</section></div></main>;
}
