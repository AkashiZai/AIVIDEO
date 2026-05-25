// ===========================================================================
// VideoPreview — HTML5 video player with custom controls
// ===========================================================================

import { useRef, useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';

interface VideoPreviewProps {
  src: string;
  showControls?: boolean;
  onTimeUpdate?: (time: number) => void;
}

export interface VideoPreviewHandle {
  getCurrentTime: () => number;
  getDuration: () => number;
}

export const VideoPreview = forwardRef<VideoPreviewHandle, VideoPreviewProps>(
  ({ src, showControls = true, onTimeUpdate }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);

    useImperativeHandle(ref, () => ({
      getCurrentTime: () => videoRef.current?.currentTime ?? 0,
      getDuration: () => videoRef.current?.duration ?? 0,
    }));

    const togglePlay = useCallback(() => {
      const v = videoRef.current;
      if (!v) return;
      if (v.paused) {
        v.play();
        setIsPlaying(true);
      } else {
        v.pause();
        setIsPlaying(false);
      }
    }, []);

    const handleTimeUpdate = useCallback(() => {
      const v = videoRef.current;
      if (!v) return;
      setCurrentTime(v.currentTime);
      onTimeUpdate?.(v.currentTime);
    }, [onTimeUpdate]);

    const handleLoadedMetadata = useCallback(() => {
      if (videoRef.current) {
        setDuration(videoRef.current.duration);
      }
    }, []);

    const handleScrub = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
      const t = parseFloat(e.target.value);
      if (videoRef.current) {
        videoRef.current.currentTime = t;
        setCurrentTime(t);
      }
    }, []);

    useEffect(() => {
      setIsPlaying(false);
      setCurrentTime(0);
    }, [src]);

    const formatTime = (s: number) => {
      const m = Math.floor(s / 60);
      const sec = Math.floor(s % 60);
      return `${m}:${sec.toString().padStart(2, '0')}`;
    };

    return (
      <div className="video-preview-container" id="video-preview">
        <video
          ref={videoRef}
          src={src}
          className="video-element"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
          playsInline
        />
        {showControls && (
          <div className="video-controls">
            <button className="btn btn-icon btn-ghost" onClick={togglePlay} id="btn-play-pause">
              {isPlaying ? '⏸' : '▶'}
            </button>
            <span className="video-time">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
            <input
              type="range"
              className="video-scrubber"
              min={0}
              max={duration || 1}
              step={0.1}
              value={currentTime}
              onChange={handleScrub}
              id="video-scrubber"
            />
          </div>
        )}
      </div>
    );
  },
);

VideoPreview.displayName = 'VideoPreview';
