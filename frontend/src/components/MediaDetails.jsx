import { useEffect, useRef, useState } from 'react';
import { X, Play, Plus, Check, ArrowLeft, Film } from 'lucide-react';
import { api, artwork, jf, timeLabel } from '../api';
import { useFocusScope } from '../hooks/useTVNavigation';
export default function MediaDetails({item, onClose, onPlay}) {
  const root = useRef(null);
  const [selected, setSelected] = useState(item), [data, setData] = useState(null), [children, setChildren] = useState([]);
  const [history, setHistory] = useState([]), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useFocusScope(root);
  useEffect(() => {
    let alive = true; setData(null); setChildren([]); setError('');
    api(`/media/items/${selected.Id}`).then(async result => {
      if (!alive) return; setData(result);
      if (result.IsFolder) {
        const childItems = await api(`/media/items/${selected.Id}/children`);
        if (alive) setChildren(childItems.Items);
      }
    }).catch(e => {if (alive) setError(e.message);});
    return () => {alive = false;};
  }, [selected.Id]);
  const current = data || selected, image = artwork(current, true);
  async function favorite() {
    setBusy(true); setError('');
    try {const value = await api(`/media/items/${current.Id}/favorite`, {method: current.UserData?.IsFavorite ? 'DELETE' : 'POST'}); setData({...current, UserData: value});}
    catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  async function watched() {
    setBusy(true);
    try {const user = await api('/auth/me'); const value = await jf(`Users/${user.Id}/PlayedItems/${current.Id}`, {method: current.UserData?.Played ? 'DELETE' : 'POST'}); setData({...current, UserData: value});}
    catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  async function trailer() {
    setBusy(true); setError('');
    try {const trailers = await jf(`Items/${current.Id}/LocalTrailers`); if (trailers.length) onPlay(trailers[0]); else setError('No local trailer is available. Add a trailer to this title in Jellyfin.');}
    catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  return <div className="fixed inset-0 z-40 flex items-center justify-center overflow-y-auto bg-black/80 p-3 backdrop-blur-md md:p-8" onClick={e => {if (e.target === e.currentTarget) onClose();}}><section ref={root} role="dialog" aria-modal="true" aria-label={current.Name} data-focus-scope className="relative max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-white/10 bg-canvas shadow-cinema"><div className="relative min-h-64 md:min-h-80">{image && <img src={image} alt="" className="absolute inset-0 h-full w-full object-cover"/>}<div className="absolute inset-0 bg-gradient-to-t from-canvas to-transparent"/><div className="relative flex justify-between p-5">{history.length ? <button className="icon-btn" aria-label="Back to parent" onClick={() => {setSelected(history.at(-1)); setHistory(h => h.slice(0, -1));}}><ArrowLeft/></button> : <span/>}<button className="icon-btn" onClick={onClose} aria-label="Close details"><X/></button></div></div><div className="relative -mt-16 px-6 pb-8 md:px-10"><p className="eyebrow">{current.Type?.replace(/([a-z])([A-Z])/g, '$1 $2')}</p><h2 className="mt-3 text-3xl font-bold md:text-5xl">{current.Name}</h2><p className="mt-4 text-xs text-muted">{[current.AlbumArtist || current.Artists?.join(', '), current.Album, current.ProductionYear, current.OfficialRating, current.RunTimeTicks && timeLabel(current.RunTimeTicks), current.Genres?.join(' · ')].filter(Boolean).join('  ·  ')}</p><div className="my-6 flex flex-wrap gap-3">{!current.IsFolder && <button className="btn-primary" onClick={() => onPlay(current)}><Play size={18}/>{current.UserData?.PlaybackPositionTicks ? 'Resume' : 'Play now'}</button>}<button className="btn-secondary" disabled={busy || !data} onClick={favorite}>{current.UserData?.IsFavorite ? <Check size={18}/> : <Plus size={18}/>}My list</button>{!current.IsFolder && <button className="btn-secondary" disabled={busy} onClick={watched}>{current.UserData?.Played ? 'Mark unwatched' : 'Mark watched'}</button>}{['Movie', 'Series'].includes(current.Type) && <button className="btn-secondary" disabled={busy} onClick={trailer}><Film size={17}/>Trailer</button>}</div>{error && <p role="alert" className="mb-4 text-sm text-red-300">{error}</p>}<p className="max-w-2xl text-sm leading-7 text-slate-300">{current.Overview}</p>{!data && !error && <p role="status" className="mt-4 text-muted">Loading details…</p>}{current.People?.length > 0 && <p className="mt-5 text-xs leading-6 text-muted">Cast: {current.People.filter(p => p.Type === 'Actor').slice(0, 8).map(p => p.Name).join(', ')}</p>}{children.length > 0 && <div className="mt-8"><h3 className="mb-4 text-lg font-semibold">{current.Type === 'Series' ? 'Seasons' : current.Type === 'Season' ? 'Episodes' : 'In this collection'}</h3><div className="space-y-2">{children.map(child => <button key={child.Id} className="flex w-full items-center gap-4 rounded-lg bg-white/5 p-3 text-left hover:bg-white/10" onClick={() => {if (child.IsFolder) {setHistory(h => [...h, current]); setSelected(child);} else onPlay(child);}}><span className="flex h-10 w-10 items-center justify-center rounded bg-white/5 text-accent">{child.IndexNumber || <Play size={16}/>}</span><div className="min-w-0 flex-1"><h4 className="truncate text-sm font-semibold">{child.Name}</h4><p className="mt-1 line-clamp-1 text-xs text-muted">{child.Overview || child.Type}</p></div><span className="text-xs text-muted">{child.RunTimeTicks ? timeLabel(child.RunTimeTicks) : ''}</span></button>)}</div></div>}</div></section></div>;
}
