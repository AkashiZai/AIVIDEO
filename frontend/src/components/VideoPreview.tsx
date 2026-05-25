import { useRef, useState, useCallback, forwardRef, useImperativeHandle, useEffect } from 'react';

interface Props { src: string; showControls?: boolean; onTimeUpdate?: (t: number) => void; }
export interface VideoPreviewHandle { getCurrentTime: () => number; getDuration: () => number; }

export const VideoPreview = forwardRef<VideoPreviewHandle, Props>(({ src, showControls = true, onTimeUpdate }, ref) => {
  const vRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);

  useImperativeHandle(ref, () => ({ getCurrentTime: () => vRef.current?.currentTime ?? 0, getDuration: () => vRef.current?.duration ?? 0 }));
  const toggle = useCallback(() => { const v = vRef.current; if (!v) return; v.paused ? v.play() : v.pause(); setPlaying(!v.paused); }, []);
  useEffect(() => { setPlaying(false); setTime(0); }, [src]);
  const fmt = (s: number) => `${Math.floor(s/60)}:${Math.floor(s%60).toString().padStart(2,'0')}`;

  return (
    <div className="video-preview-container">
      <video ref={vRef} src={src} className="video-element" playsInline
        onTimeUpdate={() => { const t = vRef.current?.currentTime ?? 0; setTime(t); onTimeUpdate?.(t); }}
        onLoadedMetadata={() => setDur(vRef.current?.duration ?? 0)}
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}/>
      {showControls && <div className="video-controls">
        <button className="btn btn-icon btn-ghost" onClick={toggle}>{playing ? '⏸' : '▶'}</button>
        <span className="video-time">{fmt(time)} / {fmt(dur)}</span>
        <input type="range" className="video-scrubber" min={0} max={dur||1} step={0.1} value={time} onChange={(e)=>{const t=parseFloat(e.target.value);if(vRef.current)vRef.current.currentTime=t;setTime(t)}}/>
      </div>}
    </div>
  );
});
VideoPreview.displayName = 'VideoPreview';
