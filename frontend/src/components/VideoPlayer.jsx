import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js/dist/hls.light.mjs';
import { X, Maximize, SkipBack, SkipForward, Play, Pause, Volume2, Music2, Gauge, Layers, AudioLines, Captions, Timer, BookOpen, Check, Wrench } from 'lucide-react';
import { api, artwork, post } from '../api';
import { useFocusScope } from '../hooks/useTVNavigation';

function MenuButton({icon: Icon, label, value, options, onChange}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = e => {if (!ref.current?.contains(e.target)) setOpen(false);};
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [open]);
  return <div ref={ref} className="relative" onKeyDown={e => {if (open && e.key === 'Escape') {e.stopPropagation(); e.preventDefault(); setOpen(false);}}}>
    <button className="icon-btn" aria-label={label} aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(o => !o)}><Icon size={18}/></button>
    {open && <div role="listbox" aria-label={label} className="absolute bottom-full left-1/2 z-20 mb-2 max-h-64 w-56 -translate-x-1/2 overflow-y-auto rounded-xl border border-white/10 bg-canvas/95 p-2 shadow-cinema backdrop-blur-xl">
      <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">{label}</p>
      {options.map(o => <button key={o.value} role="option" aria-selected={o.value === value} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${o.value === value ? 'bg-accent/10 text-accent' : 'text-slate-200 hover:bg-white/5'}`} onClick={() => {onChange(o.value); setOpen(false);}}>{o.label}{o.value === value && <Check size={15}/>}</button>)}
    </div>}
  </div>;
}

export default function VideoPlayer({item, onClose, onEnded}) {
  const root = useRef(null), video = useRef(null), latest = useRef(null), position = useRef(item.UserData?.PlaybackPositionTicks || 0);
  const [options, setOptions] = useState({start_ticks: position.current, subtitle_index: -1});
  const [info, setInfo] = useState(null), [error, setError] = useState(''), [playing, setPlaying] = useState(false);
  const [status, setStatus] = useState('Preparing your stream…'), [offset, setOffset] = useState(0), [subtitle, setSubtitle] = useState(-1);
  const originalCueTimes = useRef(new WeakMap());
  useFocusScope(root);

  useEffect(() => {
    let disposed = false, hls, interval, negotiated, loaded, started = false;
    const media = video.current;
    const report = event => {
      if (!negotiated || !started) return;
      const payload = {ItemId: item.Id, MediaSourceId: negotiated.source_id,
        PlaySessionId: negotiated.play_session_id, PositionTicks: Math.round(position.current),
        IsPaused: media.paused, IsMuted: media.muted, VolumeLevel: Math.round(media.volume * 100),
        PlayMethod: negotiated.method, LiveStreamId: negotiated.live_stream_id};
      api(`/playback/events/${event}`, {method: 'POST', body: JSON.stringify(payload), keepalive: event === 'stop'}).catch(e => { if (!disposed) setStatus(`Progress sync: ${e.message}`); });
    };
    function start() {setPlaying(true); setStatus(''); if (!started) {started = true; report('start');} else report('progress');}
    function pause() {setPlaying(false); report('progress');}
    function update() {
      if (!negotiated || !Number.isFinite(media.currentTime)) return;
      const base = negotiated.method === 'Transcode' ? negotiated.start_ticks : 0;
      position.current = base + media.currentTime * 10000000;
    }
    function ended() {report('stop'); started = false; onEnded?.();}
    function failed() {setError('This stream could not be played. Try compatibility mode or a lower quality.');}
    function unload() {report('stop');}
    media.addEventListener('playing', start); media.addEventListener('pause', pause);
    media.addEventListener('timeupdate', update); media.addEventListener('ended', ended); media.addEventListener('error', failed);
    window.addEventListener('pagehide', unload);
    setInfo(null); setError(''); setStatus('Preparing your stream…');
    post(`/playback/${item.Id}/info`, options).then(result => {
      if (disposed) {
        post('/playback/events/stop', {ItemId: item.Id, MediaSourceId: result.source_id, PlaySessionId: result.play_session_id,
          PositionTicks: options.start_ticks || 0, PlayMethod: result.method, LiveStreamId: result.live_stream_id}).catch(() => {});
        return;
      }
      negotiated = result; latest.current = result; setInfo(result);
      if (result.url.includes('.m3u8') && Hls.isSupported()) {
        hls = new Hls({enableWorker: true, maxBufferLength: 30});
        hls.loadSource(result.url); hls.attachMedia(media);
        hls.on(Hls.Events.ERROR, (_event, data) => {if (data.fatal) setError(`Stream interrupted (${data.type}). Try compatibility mode.`);});
      } else {media.src = result.url;}
      loaded = () => {
        if (result.method === 'DirectPlay' && options.start_ticks && Number.isFinite(media.duration)) media.currentTime = options.start_ticks / 10000000;
        media.play().catch(() => setStatus('Press play to start.'));
      };
      media.addEventListener('loadedmetadata', loaded, {once: true});
      interval = setInterval(() => report('progress'), 10000);
    }).catch(e => {if (!disposed) setError(e.message);});
    return () => {
      disposed = true; clearInterval(interval); report('stop');
      if (loaded) media.removeEventListener('loadedmetadata', loaded);
      media.removeEventListener('playing', start); media.removeEventListener('pause', pause);
      media.removeEventListener('timeupdate', update); media.removeEventListener('ended', ended); media.removeEventListener('error', failed);
      window.removeEventListener('pagehide', unload);
      hls?.destroy(); media.pause(); media.removeAttribute('src'); media.load();
    };
  }, [item.Id, options, onEnded]);

  useEffect(() => {
    const media = video.current;
    const update = () => {
      for (const track of media.textTracks) {
        track.mode = track.id === String(subtitle) ? 'showing' : 'disabled';
        if (track.cues) for (const cue of track.cues) {
          if (!originalCueTimes.current.has(cue)) originalCueTimes.current.set(cue, [cue.startTime, cue.endTime]);
          const [start, end] = originalCueTimes.current.get(cue);
          const base = info?.method === 'Transcode' ? info.start_ticks / 10000000 : 0;
          cue.startTime = Math.max(0, start + offset - base); cue.endTime = Math.max(0, end + offset - base);
        }
      }
    };
    update(); const timer = setInterval(update, 500);
    return () => clearInterval(timer);
  }, [offset, subtitle, info]);

  function change(values) {setOptions(previous => ({...previous, start_ticks: Math.round(position.current), ...values}));}
  function seek(seconds) {
    const target = Math.max(0, position.current / 10000000 + seconds);
    const base = info?.method === 'Transcode' ? info.start_ticks / 10000000 : 0;
    const local = target - base, media = video.current;
    if (local >= 0 && media.seekable.length && local <= media.seekable.end(media.seekable.length - 1)) media.currentTime = local;
    else change({start_ticks: Math.round(target * 10000000)});
  }
  function selectSubtitle(value) {
    const index = Number(value); setSubtitle(index);
    const external = info?.subtitles.some(s => s.index === index);
    if (!external || options.subtitle_index !== -1) change({subtitle_index: external ? -1 : index});
  }
  async function fullscreen() {try {if (document.fullscreenElement) await document.exitFullscreen(); else await root.current.requestFullscreen();} catch {setStatus('Fullscreen is not available on this device.');}}
  const isAudio = !!info && !info.streams?.some(s => s.Type === 'Video');
  const cover = artwork(item, true) || artwork(item);
  return <div ref={root} role="dialog" aria-modal="true" aria-label={`Playing ${item.Name}`} data-focus-scope className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-black">
    <header className="flex items-center justify-between gap-4 px-6 py-4"><div><p className="eyebrow">Now playing</p><h2 className="mt-1 font-semibold">{item.Name}</h2></div><button className="icon-btn" onClick={onClose} aria-label="Close player"><X/></button></header>
    {isAudio && <div className="relative flex min-h-0 w-full flex-1 items-center justify-center overflow-hidden bg-black">{cover && <img src={cover} alt="" className="absolute inset-0 h-full w-full scale-110 object-cover opacity-30 blur-2xl"/>}{cover ? <img src={cover} alt="" className="relative z-10 h-56 w-56 rounded-lg object-cover shadow-cinema md:h-72 md:w-72"/> : <Music2 size={72} className="relative z-10 text-slate-600"/>}</div>}
    {/* display:none can pause playback on some browsers (iOS Safari); stay rendered but visually negligible instead. */}
    <video ref={video} controls={!isAudio} playsInline className={isAudio ? 'absolute h-px w-px overflow-hidden opacity-0' : 'min-h-0 w-full flex-1 bg-black'} aria-label={item.Name} crossOrigin="anonymous">{info?.subtitles.map(s => <track key={s.index} id={String(s.index)} kind="subtitles" src={s.url} srcLang={s.language} label={s.label}/>)}</video>
    <div className="bg-canvas p-5 md:px-10">{error && <p role="alert" className="mb-3 text-sm text-red-300">{error}</p>}{status && <p role="status" className="mb-3 text-xs text-muted">{status}</p>}<div className="flex flex-wrap items-center gap-3"><button className="icon-btn" aria-label={playing ? 'Pause' : 'Play'} onClick={() => playing ? video.current.pause() : video.current.play().catch(e => setError(e.message))}>{playing ? <Pause size={18}/> : <Play size={18}/>}</button><button className="icon-btn" aria-label="Back 10 seconds" onClick={() => seek(-10)}><SkipBack size={18}/></button><button className="icon-btn" aria-label="Forward 30 seconds" onClick={() => seek(30)}><SkipForward size={18}/></button><button className="icon-btn" aria-label="Toggle mute" onClick={() => {video.current.muted = !video.current.muted;}}><Volume2 size={18}/></button>{!isAudio && <button className="icon-btn" aria-label="Fullscreen" onClick={fullscreen}><Maximize size={18}/></button>}<span className="mr-auto text-xs text-muted">{info?.method === 'DirectPlay' ? 'Direct play' : info ? 'Transcoding' : 'Connecting'}</span>
      <MenuButton icon={Gauge} label="Quality" value={options.max_bitrate || 20000000} onChange={v => change({max_bitrate: v, force_transcode: true})} options={[{value: 20000000, label: 'Auto · up to 20 Mbps'}, {value: 8000000, label: '8 Mbps'}, {value: 4000000, label: '4 Mbps'}, {value: 1500000, label: '1.5 Mbps'}]}/>
      {!!info?.sources.length && <MenuButton icon={Layers} label="Version" value={info.source_id} onChange={v => change({media_source_id: v})} options={info.sources.map(s => ({value: s.id, label: s.name}))}/>}
      <MenuButton icon={AudioLines} label="Audio" value={options.audio_index ?? ''} onChange={v => change({audio_index: v === '' ? null : v, force_transcode: true})} options={[{value: '', label: 'Default'}, ...(info?.streams.filter(s => s.Type === 'Audio').map(s => ({value: s.Index, label: s.DisplayTitle || s.Language || `Track ${s.Index}`})) || [])]}/>
      <MenuButton icon={Captions} label="Subtitles" value={subtitle} onChange={selectSubtitle} options={[{value: -1, label: 'Off'}, ...(info?.streams.filter(s => s.Type === 'Subtitle').map(s => ({value: s.Index, label: s.DisplayTitle || s.Language || `Track ${s.Index}`})) || [])]}/>
      {subtitle !== -1 && <label className="text-xs text-muted"><span className="flex items-center gap-1.5"><Timer size={13}/>Subtitle delay (s)</span><input type="number" step="0.25" min="-30" max="30" className="field mt-1 w-28" value={offset} onChange={e => setOffset(Number(e.target.value))}/></label>}
      {!!item.Chapters?.length && <MenuButton icon={BookOpen} label="Chapters" value={null} onChange={v => change({start_ticks: v})} options={item.Chapters.map((c, i) => ({value: c.StartPositionTicks, label: c.Name || `Chapter ${i + 1}`}))}/>}
      <button className="icon-btn" aria-label="Compatibility mode: force a more widely supported format if playback is failing" onClick={() => change({force_transcode: true})}><Wrench size={18}/></button>
    </div></div>
  </div>;
}
