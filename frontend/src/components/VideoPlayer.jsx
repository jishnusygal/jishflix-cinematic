import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js/dist/hls.light.mjs';
import { X, Maximize, SkipBack, SkipForward, Play, Pause, Volume2 } from 'lucide-react';
import { api, post } from '../api';
import { useFocusScope } from '../hooks/useTVNavigation';

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
  return <div ref={root} role="dialog" aria-modal="true" aria-label={`Playing ${item.Name}`} data-focus-scope className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-black">
    <header className="flex items-center justify-between gap-4 px-6 py-4"><div><p className="eyebrow">Now playing</p><h2 className="mt-1 font-semibold">{item.Name}</h2></div><button className="icon-btn" onClick={onClose} aria-label="Close player"><X/></button></header>
    <video ref={video} controls playsInline className="min-h-0 w-full flex-1 bg-black" aria-label={item.Name} crossOrigin="anonymous">{info?.subtitles.map(s => <track key={s.index} id={String(s.index)} kind="subtitles" src={s.url} srcLang={s.language} label={s.label}/>)}</video>
    <div className="bg-canvas p-5 md:px-10">{error && <p role="alert" className="mb-3 text-sm text-red-300">{error}</p>}{status && <p role="status" className="mb-3 text-xs text-muted">{status}</p>}<div className="flex flex-wrap items-center gap-3"><button className="icon-btn" aria-label={playing ? 'Pause' : 'Play'} onClick={() => playing ? video.current.pause() : video.current.play().catch(e => setError(e.message))}>{playing ? <Pause size={18}/> : <Play size={18}/>}</button><button className="icon-btn" aria-label="Back 10 seconds" onClick={() => seek(-10)}><SkipBack size={18}/></button><button className="icon-btn" aria-label="Forward 30 seconds" onClick={() => seek(30)}><SkipForward size={18}/></button><button className="icon-btn" aria-label="Toggle mute" onClick={() => {video.current.muted = !video.current.muted;}}><Volume2 size={18}/></button><button className="icon-btn" aria-label="Fullscreen" onClick={fullscreen}><Maximize size={18}/></button><span className="mr-auto text-xs text-muted">{info?.method === 'DirectPlay' ? 'Direct play' : info ? 'Transcoding' : 'Connecting'}</span>
      <label className="text-xs text-muted">Quality<select className="field mt-1" value={options.max_bitrate || 20000000} onChange={e => change({max_bitrate: Number(e.target.value), force_transcode: true})}><option value={20000000}>Auto · up to 20 Mbps</option><option value={8000000}>8 Mbps</option><option value={4000000}>4 Mbps</option><option value={1500000}>1.5 Mbps</option></select></label>
      {!!info?.sources.length && <label className="text-xs text-muted">Version<select className="field mt-1 max-w-48" value={info.source_id} onChange={e => change({media_source_id: e.target.value})}>{info.sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
      <label className="text-xs text-muted">Audio<select className="field mt-1 max-w-52" value={options.audio_index ?? ''} onChange={e => change({audio_index: e.target.value === '' ? null : Number(e.target.value), force_transcode: true})}><option value="">Default</option>{info?.streams.filter(s => s.Type === 'Audio').map(s => <option key={s.Index} value={s.Index}>{s.DisplayTitle || s.Language || `Track ${s.Index}`}</option>)}</select></label>
      <label className="text-xs text-muted">Subtitles<select className="field mt-1 max-w-52" value={subtitle} onChange={e => selectSubtitle(e.target.value)}><option value={-1}>Off</option>{info?.streams.filter(s => s.Type === 'Subtitle').map(s => <option key={s.Index} value={s.Index}>{s.DisplayTitle || s.Language || `Track ${s.Index}`}</option>)}</select></label>
      {subtitle !== -1 && <label className="text-xs text-muted">Subtitle delay (s)<input type="number" step="0.25" min="-30" max="30" className="field mt-1 w-28" value={offset} onChange={e => setOffset(Number(e.target.value))}/></label>}
      {!!item.Chapters?.length && <label className="text-xs text-muted">Chapters<select className="field mt-1 max-w-48" defaultValue="" onChange={e => {if (e.target.value) change({start_ticks: Number(e.target.value)});}}><option value="">Jump to chapter</option>{item.Chapters.map((c, i) => <option key={i} value={c.StartPositionTicks}>{c.Name || `Chapter ${i + 1}`}</option>)}</select></label>}
      <button className="btn-secondary text-xs" onClick={() => change({force_transcode: true})}>Compatibility mode</button>
    </div></div>
  </div>;
}
