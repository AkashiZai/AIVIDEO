// ===========================================================================
// StyleStep — Caption style selection with live preview
// ===========================================================================

import { useState, useRef } from 'react';
import { useStore } from '../store';
import { CAPTION_STYLES, FONT_SIZES } from '../types';
import type { CaptionStyleType, FontSize, CaptionPosition } from '../types';
import { ColorPicker } from './ColorPicker';
import { VideoPreview, type VideoPreviewHandle } from './VideoPreview';
import { CaptionOverlay } from './CaptionOverlay';
import { WaveformVisualizer } from './WaveformVisualizer';

const POSITIONS: { value: CaptionPosition; label: string }[] = [
  { value: 'top', label: 'Top' },
  { value: 'center', label: 'Center' },
  { value: 'bottom', label: 'Bottom' },
];

export function StyleStep() {
  const {
    videoUrl, segments, videoDuration, setStep,
    captionStyle, setCaptionStyle,
    fontSize, setFontSize,
    textColor, setTextColor,
    position, setPosition,
  } = useStore();

  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef<VideoPreviewHandle>(null);

  return (
    <div className="style-step">
      {/* Style cards */}
      <div className="style-cards" id="style-cards">
        {CAPTION_STYLES.map((s) => (
          <button
            key={s.value}
            className={`style-card ${captionStyle === s.value ? 'active' : ''}`}
            onClick={() => setCaptionStyle(s.value as CaptionStyleType)}
            id={`style-${s.value}`}
            type="button"
          >
            <div className="style-card-icon">{s.icon}</div>
            <div className="style-card-label">{s.label}</div>
            <div className="style-card-desc">{s.description}</div>
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="style-controls" id="style-controls">
        <div className="style-control-group">
          <label>Font Size</label>
          <div className="toggle-group">
            {FONT_SIZES.map((f) => (
              <button
                key={f.value}
                className={`toggle-btn ${fontSize === f.value ? 'active' : ''}`}
                onClick={() => setFontSize(f.value as FontSize)}
                type="button"
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div className="style-control-group">
          <label>Position</label>
          <div className="toggle-group">
            {POSITIONS.map((p) => (
              <button
                key={p.value}
                className={`toggle-btn ${position === p.value ? 'active' : ''}`}
                onClick={() => setPosition(p.value as CaptionPosition)}
                type="button"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="style-control-group">
          <label>Text Color</label>
          <ColorPicker value={textColor} onChange={setTextColor} />
        </div>
      </div>

      {/* Live preview */}
      {videoUrl && (
        <>
          <div className="style-preview" id="style-preview">
            <VideoPreview
              ref={videoRef}
              src={videoUrl}
              showControls
              onTimeUpdate={setCurrentTime}
            />
            <CaptionOverlay
              segments={segments}
              style={captionStyle}
              fontSize={fontSize}
              textColor={textColor}
              position={position}
              currentTime={currentTime}
            />
          </div>

          <WaveformVisualizer
            videoUrl={videoUrl}
            currentTime={currentTime}
            duration={videoDuration}
          />
        </>
      )}

      {/* Navigation */}
      <div className="step-nav">
        <button className="btn btn-ghost" onClick={() => setStep(2)} id="btn-back-transcribe">
          ← Back
        </button>
        <button
          className="btn btn-primary btn-large"
          onClick={() => setStep(4)}
          id="btn-next-export"
        >
          Next: Export →
        </button>
      </div>
    </div>
  );
}
