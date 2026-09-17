import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Search, Clapperboard, ArrowRight, RefreshCw, LibraryBig } from 'lucide-react';
import { api, jf } from './api';
import useTVNavigation from './hooks/useTVNavigation';
import AuthScreen from './components/AuthScreen';
import Sidebar from './components/Sidebar';
import HeroBanner from './components/HeroBanner';
import MediaRow from './components/MediaRow';
import MediaCard from './components/MediaCard';
import MediaDetails from './components/MediaDetails';
import LiveTV from './components/LiveTV';
import Settings from './components/Settings';
import SetupWizard from './components/SetupWizard';
const VideoPlayer = lazy(() => import('./components/VideoPlayer'));

function Loading({text = 'Finding your next great story…'}) {return <div className="flex min-h-[50vh] items-center justify-center gap-3 px-6 text-sm text-muted" role="status"><RefreshCw size={18} className="animate-spin text-accent"/>{text}</div>;}
function ErrorState({message, retry}) {return <div role="alert" className="mx-6 my-32 rounded-xl border border-red-400/20 bg-red-500/5 p-8"><h2 className="text-xl font-semibold">Something interrupted the show.</h2><p className="my-4 text-sm text-red-200">{message}</p><button className="btn-secondary" onClick={retry}>Try again</button></div>;}

function Home({onSelect, onPlay, revision}) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [attempt, setAttempt] = useState(0), [heroIndex, setHeroIndex] = useState(0);
  useEffect(() => {let active = true; api('/media/home').then(result => {if(active) {setData(result); setError(''); setHeroIndex(0);}}).catch(e => {if(active) setError(e.message);}); return () => {active = false;};}, [attempt, revision]);
  const backdropped = data ? [...new Map([...data.discover, ...data.recent].filter(i => i.BackdropImageTags?.length).map(i => [i.Id, i])).values()].slice(0, 5) : [];
  const heroes = backdropped.length ? backdropped : (data?.recent[0] ? [data.recent[0]] : []);
  useEffect(() => {
    if (heroes.length < 2) return;
    const timer = setInterval(() => setHeroIndex(i => (i + 1) % heroes.length), 9000);
    return () => clearInterval(timer);
  }, [heroes.length]);
  if (error) return <ErrorState message={error} retry={() => setAttempt(a => a + 1)}/>;
  if (!data) return <Loading/>;
  return <><HeroBanner item={heroes[heroIndex]} onPlay={onPlay} onSelect={onSelect} total={heroes.length} active={heroIndex} onPick={setHeroIndex}/><div className="relative -mt-8 pb-8"><MediaRow title="Pick up where you left off" subtitle="Your stories are waiting." items={data.continue} onSelect={onSelect} wide/><MediaRow title="Up next" items={data.next_up} onSelect={onSelect} wide/><MediaRow title="Fresh in your library" items={data.recent} onSelect={onSelect}/><MediaRow title="Worth a night in" subtitle="Top-rated in your collection" items={data.discover} onSelect={onSelect}/><MediaRow title="Your list, your kind of cinema" items={data.favorites} onSelect={onSelect}/></div></>;
}

function Browse({user, onSelect}) {
  const [query, setQuery] = useSearchParams(), [result, setResult] = useState(null), [error, setError] = useState(''), [attempt, setAttempt] = useState(0);
  const [input, setInput] = useState(query.get('search') || ''), [genres, setGenres] = useState([]);
  const serialized = query.toString(), types = query.get('types') || '', parent = query.get('parent') || '';
  useEffect(() => {setInput(new URLSearchParams(serialized).get('search') || '');}, [serialized]);
  useEffect(() => {
    const abort = new AbortController(); setError(''); setResult(null);
    api('/media/items?' + serialized, {signal: abort.signal}).then(setResult).catch(e => {if(e.name !== 'AbortError') setError(e.message);});
    return () => abort.abort();
  }, [serialized, attempt]);
  useEffect(() => {
    const abort = new AbortController();
    const params = new URLSearchParams({UserId: user.Id, Recursive: 'true', ...(types && {IncludeItemTypes: types}), ...(parent && {ParentId: parent})});
    jf('Items/Filters2?' + params, {signal: abort.signal})
      .then(r => setGenres((r.Genres || []).map(g => g.Name).sort((a, b) => a.localeCompare(b))))
      .catch(e => {if(e.name !== 'AbortError') setGenres([]);});
    return () => abort.abort();
  }, [user.Id, types, parent]);
  const update = values => {const next = new URLSearchParams(query); for(const [key,value] of Object.entries(values)) {if(value) next.set(key,value); else next.delete(key);} if(!('start' in values)) next.delete('start'); setQuery(next);};
  const heading = query.get('favorite') ? 'My list' : query.get('types') === 'Movie' ? 'Movies' : query.get('types') === 'Series' ? 'TV shows' : query.get('types')?.includes('Audio') ? 'Music & audiobooks' : 'Explore your library';
  return <div className="px-6 pb-12 pt-32 md:px-10 xl:px-14"><p className="eyebrow">Find your next favorite</p><h1 className="mb-7 mt-3 text-4xl font-bold">{heading}</h1><form className="mb-5 flex gap-3" onSubmit={e => {e.preventDefault(); update({search: input});}}><label className="relative flex-1"><span className="sr-only">Search your library</span><Search className="absolute left-4 top-4 text-muted" size={18}/><input className="field pl-12" type="search" value={input} onChange={e => setInput(e.target.value)} placeholder="Titles, people, and worlds to get lost in…"/></label><button className="btn-primary" type="submit">Search</button></form><div className="mb-8 flex flex-wrap gap-3"><label className="text-xs text-muted">Sort by<select className="field mt-2" value={query.get('sort') || 'SortName'} onChange={e => update({sort:e.target.value})}><option value="SortName">Title</option><option value="DateCreated">Date added</option><option value="PremiereDate">Release date</option><option value="CommunityRating">Rating</option></select></label><label className="text-xs text-muted">Order<select className="field mt-2" value={query.get('order') || 'Ascending'} onChange={e => update({order:e.target.value})}><option value="Ascending">Ascending</option><option value="Descending">Descending</option></select></label><label className="text-xs text-muted">Genre<select className="field mt-2 max-w-48" value={query.get('genre') || ''} onChange={e => update({genre:e.target.value})}><option value="">Any genre</option>{genres.map(g => <option key={g} value={g}>{g}</option>)}</select></label></div>{error ? <ErrorState message={error} retry={() => setAttempt(a => a + 1)}/> : !result ? <Loading/> : <>{result.Items.length ? <><p className="mb-5 text-xs text-muted">{result.TotalRecordCount} titles</p><div className="grid grid-cols-2 justify-items-start gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">{result.Items.map(i => <MediaCard key={i.Id} item={i} onSelect={onSelect}/>)}</div></> : <div className="py-16"><h2 className="text-xl font-semibold">No titles here yet.</h2><p className="mt-3 text-sm text-muted">Try a different search or add something new to your Jellyfin library.</p></div>}<div className="mt-10 flex items-center gap-4"><button className="btn-secondary" disabled={!Number(query.get('start'))} onClick={() => update({start:String(Math.max(0,Number(query.get('start') || 0) - 40))})}>Previous</button><span className="text-xs text-muted">Page {Math.floor(Number(query.get('start') || 0) / 40) + 1}</span><button className="btn-secondary" disabled={Number(query.get('start') || 0) + 40 >= result.TotalRecordCount} onClick={() => update({start:String(Number(query.get('start') || 0) + 40)})}>Next</button></div></>}</div>;
}

function Libraries() {
  const [data, setData] = useState(null), [error, setError] = useState('');
  useEffect(() => {const controller = new AbortController(); api('/media/libraries', {signal:controller.signal}).then(r => setData(r.Items)).catch(e => {if(e.name !== 'AbortError') setError(e.message);}); return () => controller.abort();}, []);
  return <div className="px-6 pb-12 pt-32 md:px-10 xl:px-14"><p className="eyebrow">All your worlds</p><h1 className="mb-8 mt-3 text-4xl font-bold">Your libraries</h1>{error && <p role="alert" className="text-red-300">{error}</p>}{!data && !error ? <Loading/> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data?.map(l => <Link key={l.Id} to={'/browse?parent=' + l.Id} className="group rounded-xl border border-white/10 bg-surface p-7 hover:border-accent/40"><LibraryBig className="mb-8 text-accent" size={32}/><div className="flex items-center justify-between"><h2 className="text-xl font-semibold">{l.Name}</h2><ArrowRight size={18}/></div><p className="mt-2 text-xs capitalize text-muted">{l.CollectionType || 'Mixed media'}</p></Link>)}</div>}{data?.length === 0 && <p className="text-muted">No libraries are visible to this profile.</p>}</div>;
}

export default function App() {
  const [user, setUser] = useState(null), [checking, setChecking] = useState(true), [detail, setDetail] = useState(null), [playing, setPlaying] = useState(null), [revision, setRevision] = useState(0);
  const navigate = useNavigate(), location = useLocation();
  useEffect(() => {api('/auth/me').then(setUser).catch(() => {}).finally(() => setChecking(false)); const expired = () => {setUser(null); setPlaying(null); setDetail(null);}; window.addEventListener('session-expired', expired); return () => window.removeEventListener('session-expired', expired);}, []);
  useTVNavigation(() => {if(playing) {setPlaying(null); setRevision(r => r + 1);} else if(detail) setDetail(null); else if(location.pathname !== '/') navigate(-1);});
  useEffect(() => {window.scrollTo(0, 0);}, [location.pathname]);
  useEffect(() => {
    if(!user) return;
    let stopped = false, socket, timer, retries = 0;
    function connect() {
      socket = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/socket`);
      socket.onopen = () => {retries = 0;};
      socket.onmessage = event => {try {const message = JSON.parse(event.data); if(['LibraryChanged','UserDataChanged'].includes(message.MessageType)) setRevision(r => r + 1);} catch { /* Non-JSON heartbeat frames have no library effect. */ }};
      socket.onclose = () => {if(!stopped) timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** retries++));};
    }
    connect(); return () => {stopped = true; clearTimeout(timer); socket?.close();};
  }, [user]);
  const play = useCallback(item => {setDetail(null); setPlaying(item);}, []);
  const finish = useCallback(() => {setPlaying(null); setRevision(r => r + 1);}, []);
  const logout = useCallback(() => {setUser(null); setPlaying(null); setDetail(null); navigate('/');}, [navigate]);
  if(checking) return <Loading text="Opening your cinema…"/>;
  if(!user) return <AuthScreen onLogin={setUser}/>;
  return <><div inert={detail || playing ? '' : undefined}><Sidebar user={user} location={location}/><div className="min-h-screen pb-20 md:ml-20 md:pb-0 xl:ml-24"><header className="absolute inset-x-0 top-0 z-20 flex h-24 items-center justify-between gap-5 bg-gradient-to-b from-canvas/80 to-transparent px-6 md:left-20 md:px-10 xl:left-24 xl:px-14"><Link to="/" className="flex items-center gap-2 text-xl font-bold tracking-tight"><Clapperboard size={22} className="text-accent md:hidden"/>jishflix<span className="ml-1 hidden text-[9px] font-medium uppercase tracking-[.25em] text-muted sm:inline">cinematic</span></Link><div className="flex items-center gap-5"><span className="hidden text-xs text-slate-300 lg:block">Your evening. Your way.</span><Link to="/browse" aria-label="Search" className="icon-btn"><Search size={18}/></Link><Link to="/settings" className="flex items-center gap-2 text-xs text-slate-300"><span className="h-1.5 w-1.5 rounded-full bg-accent"/>{user.Name}</Link></div></header><main id="main-content"><Routes><Route path="/" element={<Home onSelect={setDetail} onPlay={play} revision={revision}/>}/><Route path="/browse" element={<Browse user={user} onSelect={setDetail}/>}/><Route path="/libraries" element={<Libraries/>}/><Route path="/live" element={<LiveTV onPlay={play}/>}/><Route path="/settings" element={<Settings user={user} onLogout={logout}/>}/><Route path="/setup" element={user.Policy?.IsAdministrator ? <SetupWizard/> : <Navigate to="/settings" replace/>}/><Route path="*" element={<div className="p-12 pt-40"><h1 className="text-3xl font-bold">This scene is missing.</h1><Link className="btn-primary mt-5" to="/">Back home</Link></div>}/></Routes></main><footer className="flex justify-between border-t border-white/5 px-6 py-6 text-[10px] uppercase tracking-widest text-slate-600 md:px-10 xl:px-14"><span>Jishflix Cinematic</span><span>Your media. Your home.</span></footer></div></div>{detail && <MediaDetails key={detail.Id} item={detail} onClose={() => {setDetail(null); setRevision(r => r + 1);}} onPlay={play}/>}<Suspense fallback={<div className="fixed inset-0 z-50 bg-black"><Loading text="Preparing the player…"/></div>}>{playing && <VideoPlayer key={playing.Id} item={playing} onClose={finish} onEnded={finish}/>}</Suspense></>;
}
