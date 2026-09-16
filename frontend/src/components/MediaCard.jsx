import { Film, Play } from 'lucide-react';
import { artwork, minutes } from '../api';
export default function MediaCard({item, onSelect, wide = false}) {
  const image = artwork(item, wide);
  const progress = item.UserData?.PlayedPercentage || 0;
  return <button onClick={() => onSelect(item)} className={`media-focus group relative shrink-0 rounded-lg text-left ${wide ? 'w-64 md:w-80' : 'w-36 md:w-44 xl:w-48'}`} aria-label={`Open ${item.Name}`}>
    <div className={`relative overflow-hidden rounded-lg bg-surface ${wide ? 'aspect-video' : 'aspect-[2/3]'}`}>
      {image ? <img src={image} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" onError={e => {e.currentTarget.style.visibility = 'hidden';}}/> : <div className="flex h-full items-center justify-center bg-gradient-to-br from-slate-800 to-slate-950"><Film size={36} className="text-slate-600"/></div>}
      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent"/>
      {item.CommunityRating > 0 && <span className="absolute right-2 top-2 rounded bg-black/60 px-2 py-1 text-[10px] font-semibold backdrop-blur">★ {item.CommunityRating.toFixed(1)}</span>}
      <span className="absolute left-1/2 top-1/2 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-black opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"><Play size={20} fill="currentColor"/></span>
      {wide && progress > 0 && <div className="absolute inset-x-0 bottom-0 h-1 bg-white/20"><div className="h-full bg-accent" style={{width: `${Math.min(100, progress)}%`}}/></div>}
    </div>
    <h3 className="mt-3 truncate text-sm font-semibold text-slate-100">{item.SeriesName || item.Name}</h3>
    <p className="mt-1 truncate text-xs text-muted">{item.Type === 'Episode' ? `S${item.ParentIndexNumber || 1} · E${item.IndexNumber || 1} — ${item.Name}` : [item.ProductionYear, item.Type === 'Movie' ? 'Movie' : item.Type?.replace(/([a-z])([A-Z])/g, '$1 $2'), item.RunTimeTicks && `${minutes(item.RunTimeTicks)} min`].filter(Boolean).join(' · ')}</p>
  </button>;
}
