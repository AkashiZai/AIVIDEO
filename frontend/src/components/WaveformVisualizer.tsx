// ===========================================================================
// WaveformVisualizer — Canvas-based audio waveform
// ===========================================================================

import { useRef, useEffect, useState, useCallback } from 'react';

interface WaveformVisualizerProps {
  videoUrl: string;
  currentTime: number;
  duration: number;
  onSeek?: (time: number) => void;
}

export function WaveformVisualizer({ videoUrl, currentTime, duration, onSeek }: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [bars, setBars] = useState<Float32Array | null>(null);
  const [error, setError] = useState(false);

  // Decode audio and compute bars
  useEffect(() => {
    if (!videoUrl) return;

    let cancelled = false;
    const ac = new AudioContext();

    fetch(videoUrl)
      .then((r) => r.arrayBuffer())
      .then((buf) => ac.decodeAudioData(buf))
      .then((audioBuffer) => {
        if (cancelled) return;
        const channel = audioBuffer.getChannelData(0);
        const targetBars = 500;
        const blockSize = Math.floor(channel.length / targetBars);
        const result = new Float32Array(targetBars);

        for (let i = 0; i < targetBars; i++) {
          let peak = 0;
          const offset = i * blockSize;
          for (let j = 0; j < blockSize; j++) {
            const abs = Math.abs(channel[offset + j]);
            if (abs > peak) peak = abs;
          }
          result[i] = peak;
        }

        // Normalize
        let max = 0;
        for (let i = 0; i < result.length; i++) {
          if (result[i] > max) max = result[i];
        }
        if (max > 0) {
          for (let i = 0; i < result.length; i++) {
            result[i] /= max;
          }
        }

        setBars(result);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });

    return () => {
      cancelled = true;
      ac.close();
    };
  }, [videoUrl]);

  // Render
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !bars) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;

    ctx.clearRect(0, 0, w, h);

    const barCount = bars.length;
    const barW = w / barCount;
    const gap = Math.max(0.5, barW * 0.15);
    const centerY = h / 2;

    // Gradient
    const grad = ctx.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, '#7c5cff');
    grad.addColorStop(1, '#f472b6');
    ctx.fillStyle = grad;

    for (let i = 0; i < barCount; i++) {
      const barH = Math.max(1, bars[i] * (h * 0.85));
      const x = i * barW;
      ctx.fillRect(x + gap / 2, centerY - barH / 2, barW - gap, barH);
    }

    // Playhead
    if (duration > 0) {
      const px = (currentTime / duration) * w;
      ctx.beginPath();
      ctx.strokeStyle = '#f472b6';
      ctx.lineWidth = 2;
      ctx.moveTo(px, 0);
      ctx.lineTo(px, h);
      ctx.stroke();
    }
  }, [bars, currentTime, duration]);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onSeek || duration <= 0) return;
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      const t = (x / rect.width) * duration;
      onSeek(Math.max(0, Math.min(duration, t)));
    },
    [onSeek, duration],
  );

  if (error) {
    return (
      <div className="waveform-container">
        <div className="waveform-placeholder">Unable to load waveform</div>
      </div>
    );
  }

  return (
    <div className="waveform-container" id="waveform">
      <canvas
        ref={canvasRef}
        className="waveform-canvas"
        onClick={handleClick}
      />
    </div>
  );
}
