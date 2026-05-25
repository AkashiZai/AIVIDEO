import { useRef, useEffect, useState, useCallback } from 'react';

interface Props { videoUrl: string; currentTime: number; duration: number; onSeek?: (t: number) => void; }

export function WaveformVisualizer({ videoUrl, currentTime, duration, onSeek }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [bars, setBars] = useState<Float32Array | null>(null);

  useEffect(() => {
    if (!videoUrl) return;
    let off = false; const ac = new AudioContext();
    fetch(videoUrl).then(r => r.arrayBuffer()).then(b => ac.decodeAudioData(b)).then(ab => {
      if (off) return;
      const ch = ab.getChannelData(0), n = 500, bs = Math.floor(ch.length / n), res = new Float32Array(n);
      let mx = 0;
      for (let i = 0; i < n; i++) { let pk = 0; for (let j = 0; j < bs; j++) { const a = Math.abs(ch[i*bs+j]); if (a > pk) pk = a; } res[i] = pk; if (pk > mx) mx = pk; }
      if (mx > 0) for (let i = 0; i < n; i++) res[i] /= mx;
      setBars(res);
    }).catch(() => {});
    return () => { off = true; ac.close(); };
  }, [videoUrl]);

  useEffect(() => {
    const c = canvasRef.current; if (!c || !bars) return;
    const ctx = c.getContext('2d'); if (!ctx) return;
    const r = c.getBoundingClientRect(), dpr = devicePixelRatio || 1;
    c.width = r.width*dpr; c.height = r.height*dpr; ctx.scale(dpr, dpr);
    const w = r.width, h = r.height; ctx.clearRect(0,0,w,h);
    const bw = w/bars.length, gap = Math.max(0.5, bw*0.15), cy = h/2;
    const g = ctx.createLinearGradient(0,0,w,0); g.addColorStop(0,'#7c5cff'); g.addColorStop(1,'#f472b6'); ctx.fillStyle = g;
    for (let i = 0; i < bars.length; i++) { const bh = Math.max(1, bars[i]*(h*0.85)); ctx.fillRect(i*bw+gap/2, cy-bh/2, bw-gap, bh); }
    if (duration > 0) { const px = (currentTime/duration)*w; ctx.strokeStyle='#f472b6'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(px,0); ctx.lineTo(px,h); ctx.stroke(); }
  }, [bars, currentTime, duration]);

  const click = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onSeek || duration <= 0) return;
    const r = canvasRef.current?.getBoundingClientRect(); if (!r) return;
    onSeek(Math.max(0, Math.min(duration, ((e.clientX-r.left)/r.width)*duration)));
  }, [onSeek, duration]);

  return (<div className="waveform-container"><canvas ref={canvasRef} className="waveform-canvas" onClick={click}/></div>);
}
