import { useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import MediaCard from './MediaCard';
export default function MediaRow({title, subtitle, items = [], onSelect, wide = false}) {
  const row = useRef(null);
  if (!items.length) return null;
  const move = sign => row.current.scrollBy({left: sign * row.current.clientWidth * .8, behavior: 'smooth'});
  return <section className="mb-10" aria-label={title}>
    <div className="mb-4 flex items-end justify-between px-6 md:px-10 xl:px-14"><div><h2 className="text-xl font-semibold tracking-tight">{title}</h2>{subtitle && <p className="mt-1 text-xs text-muted">{subtitle}</p>}</div><div className="flex gap-2"><button className="icon-btn h-8 w-8" aria-label={`Scroll ${title} left`} onClick={() => move(-1)}><ChevronLeft size={16}/></button><button className="icon-btn h-8 w-8" aria-label={`Scroll ${title} right`} onClick={() => move(1)}><ChevronRight size={16}/></button></div></div>
    <div ref={row} className="flex gap-4 overflow-x-auto px-6 py-3 md:px-10 xl:px-14" style={{scrollSnapType: 'x proximity'}}>{items.map(item => <MediaCard key={item.Id} item={item} onSelect={onSelect} wide={wide}/>)}</div>
  </section>;
}
