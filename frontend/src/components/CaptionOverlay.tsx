// ===========================================================================
// CaptionOverlay — Live caption preview on top of video
// ===========================================================================

import { useMemo } from 'react';
import type { TranscriptionSegment, CaptionStyleType, FontSize, CaptionPosition } from '../types';

interface CaptionOverlayProps {
  segments: TranscriptionSegment[];
  style: CaptionStyleType;
  fontSize: FontSize;
  textColor: string;
  position: CaptionPosition;
  currentTime: number;
}

function findActiveSegment(segments: TranscriptionSegment[], time: number) {
  return segments.find((s) => time >= s.start && time < s.end) ?? null;
}

function findActiveWordIndex(segment: TranscriptionSegment, time: number): number {
  for (let i = 0; i < segment.words.length; i++) {
    if (time >= segment.words[i].start && time < segment.words[i].end) {
      return i;
    }
  }
  return -1;
}

export function CaptionOverlay({
  segments,
  style,
  fontSize,
  textColor,
  position,
  currentTime,
}: CaptionOverlayProps) {
  const activeSeg = useMemo(
    () => findActiveSegment(segments, currentTime),
    [segments, currentTime],
  );
  const activeWordIdx = useMemo(
    () => (activeSeg ? findActiveWordIndex(activeSeg, currentTime) : -1),
    [activeSeg, currentTime],
  );

  const posClass = `pos-${position}`;
  const sizeClass = `size-${fontSize}`;

  if (!activeSeg) return <div className={`caption-overlay ${posClass}`} />;

  const renderCaption = () => {
    switch (style) {
      // --- TikTok: one word at a time ---
      case 'tiktok': {
        const word = activeSeg.words[activeWordIdx];
        if (!word) return null;
        return (
          <div className={`caption-tiktok ${sizeClass}`} style={{ color: textColor }} key={word.start}>
            {word.word}
          </div>
        );
      }

      // --- Subtitle: full segment with bg bar ---
      case 'subtitle':
        return (
          <div className={`caption-subtitle ${sizeClass}`} style={{ color: textColor }}>
            {activeSeg.text}
          </div>
        );

      // --- Word-by-word: cumulative ---
      case 'word_by_word': {
        const visibleWords = activeSeg.words.filter((w) => currentTime >= w.start);
        return (
          <div className={`caption-word-by-word ${sizeClass}`} style={{ color: textColor }}>
            {visibleWords.map((w, i) => (
              <span key={i}>{w.word} </span>
            ))}
          </div>
        );
      }

      // --- Karaoke: full line, active word highlighted ---
      case 'karaoke':
        return (
          <div className={`caption-karaoke ${sizeClass}`}>
            {activeSeg.words.map((w, i) => {
              const isActive = i === activeWordIdx;
              const isSpoken = currentTime >= w.end;
              return (
                <span
                  key={i}
                  className={`karaoke-word ${isActive ? 'active' : ''} ${isSpoken ? 'spoken' : ''}`}
                  style={!isActive ? { color: textColor } : undefined}
                >
                  {w.word}{' '}
                </span>
              );
            })}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className={`caption-overlay ${posClass}`}>
      {renderCaption()}
    </div>
  );
}
