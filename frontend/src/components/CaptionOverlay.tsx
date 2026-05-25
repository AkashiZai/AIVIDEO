import { useMemo } from 'react';
import type { TranscriptionSegment, CaptionStyleType, FontSize, CaptionPosition } from '../types';

interface Props { segments: TranscriptionSegment[]; style: CaptionStyleType; fontSize: FontSize; textColor: string; position: CaptionPosition; currentTime: number; }

function findSeg(segs: TranscriptionSegment[], t: number) { return segs.find(s => t >= s.start && t < s.end) ?? null; }
function findWord(seg: TranscriptionSegment, t: number) { for (let i = 0; i < seg.words.length; i++) if (t >= seg.words[i].start && t < seg.words[i].end) return i; return -1; }

export function CaptionOverlay({ segments, style, fontSize, textColor, position, currentTime }: Props) {
  const seg = useMemo(() => findSeg(segments, currentTime), [segments, currentTime]);
  const wi = useMemo(() => seg ? findWord(seg, currentTime) : -1, [seg, currentTime]);
  const pc = `pos-${position}`, sc = `size-${fontSize}`;
  if (!seg) return <div className={`caption-overlay ${pc}`}/>;

  switch (style) {
    case 'tiktok': { const w = seg.words[wi]; return <div className={`caption-overlay ${pc}`}>{w && <div className={`caption-tiktok ${sc}`} style={{color:textColor}} key={w.start}>{w.word}</div>}</div>; }
    case 'subtitle': return <div className={`caption-overlay ${pc}`}><div className={`caption-subtitle ${sc}`} style={{color:textColor}}>{seg.text}</div></div>;
    case 'word_by_word': return <div className={`caption-overlay ${pc}`}><div className={`caption-word-by-word ${sc}`} style={{color:textColor}}>{seg.words.filter(w=>currentTime>=w.start).map((w,i)=><span key={i}>{w.word} </span>)}</div></div>;
    case 'karaoke': return <div className={`caption-overlay ${pc}`}><div className={`caption-karaoke ${sc}`}>{seg.words.map((w,i)=><span key={i} className={`karaoke-word ${i===wi?'active':''} ${currentTime>=w.end?'spoken':''}`} style={i!==wi?{color:textColor}:undefined}>{w.word} </span>)}</div></div>;
    default: return null;
  }
}
