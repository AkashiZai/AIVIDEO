import { create } from 'zustand';
import type { AppStep, CaptionStyleType, FontSize, CaptionPosition, CaptionConfig, TranscriptionSegment, Toast, WhisperModel, WordTimestamp } from './types';

interface AppStore {
  step: AppStep; setStep: (s: AppStep) => void;
  jobId: string | null; setJobId: (id: string | null) => void;
  videoUrl: string | null; setVideoUrl: (url: string | null) => void;
  videoFilename: string; setVideoFilename: (n: string) => void;
  videoDuration: number; setVideoDuration: (d: number) => void;
  segments: TranscriptionSegment[]; setSegments: (s: TranscriptionSegment[]) => void;
  updateSegmentText: (id: number, text: string) => void;
  updateWord: (segId: number, wordIdx: number, newWord: string) => void;
  language: string; setLanguage: (l: string) => void;
  detectedLanguage: string; setDetectedLanguage: (l: string) => void;

  // Transcription settings
  whisperModel: WhisperModel; setWhisperModel: (m: WhisperModel) => void;
  transcribeLang: string | null; setTranscribeLang: (l: string | null) => void;
  initialPrompt: string; setInitialPrompt: (p: string) => void;
  hotwords: string; setHotwords: (h: string) => void;

  // Caption style
  captionStyle: CaptionStyleType; setCaptionStyle: (s: CaptionStyleType) => void;
  fontSize: FontSize; setFontSize: (s: FontSize) => void;
  textColor: string; setTextColor: (c: string) => void;
  position: CaptionPosition; setPosition: (p: CaptionPosition) => void;

  // Progress
  transcribeProgress: number; setTranscribeProgress: (p: number) => void;
  exportProgress: number; setExportProgress: (p: number) => void;
  progressMessage: string; setProgressMessage: (m: string) => void;
  exportedVideoUrl: string | null; setExportedVideoUrl: (u: string | null) => void;

  // Toast
  toasts: Toast[]; addToast: (message: string, type: Toast['type']) => void; removeToast: (id: string) => void;
  getCaptionConfig: () => CaptionConfig;
  reset: () => void;
}

export const useStore = create<AppStore>((set, get) => ({
  step: 1, setStep: (step) => set({ step }),
  jobId: null, setJobId: (id) => set({ jobId: id }),
  videoUrl: null, setVideoUrl: (url) => set({ videoUrl: url }),
  videoFilename: '', setVideoFilename: (name) => set({ videoFilename: name }),
  videoDuration: 0, setVideoDuration: (d) => set({ videoDuration: d }),
  segments: [], setSegments: (segs) => set({ segments: segs }),
  updateSegmentText: (id, text) => set((s) => ({
    segments: s.segments.map((seg) => seg.id === id ? { ...seg, text } : seg),
  })),
  updateWord: (segId, wordIdx, newWord) => set((s) => ({
    segments: s.segments.map((seg) => {
      if (seg.id !== segId) return seg;
      const words = seg.words.map((w, i) => i === wordIdx ? { ...w, word: newWord } : w);
      const text = words.map((w) => w.word).join(' ');
      return { ...seg, words, text };
    }),
  })),
  language: 'en', setLanguage: (lang) => set({ language: lang }),
  detectedLanguage: '', setDetectedLanguage: (l) => set({ detectedLanguage: l }),

  // Transcription settings — default to large-v3 for best accuracy
  whisperModel: 'large-v3', setWhisperModel: (model) => set({ whisperModel: model }),
  transcribeLang: null, setTranscribeLang: (lang) => set({ transcribeLang: lang }),
  initialPrompt: '', setInitialPrompt: (prompt) => set({ initialPrompt: prompt }),
  hotwords: '', setHotwords: (hw) => set({ hotwords: hw }),

  captionStyle: 'tiktok', setCaptionStyle: (style) => set({ captionStyle: style }),
  fontSize: 'medium', setFontSize: (size) => set({ fontSize: size }),
  textColor: '#FFFFFF', setTextColor: (color) => set({ textColor: color }),
  position: 'bottom', setPosition: (pos) => set({ position: pos }),

  transcribeProgress: 0, setTranscribeProgress: (p) => set({ transcribeProgress: p }),
  exportProgress: 0, setExportProgress: (p) => set({ exportProgress: p }),
  progressMessage: '', setProgressMessage: (msg) => set({ progressMessage: msg }),
  exportedVideoUrl: null, setExportedVideoUrl: (url) => set({ exportedVideoUrl: url }),

  toasts: [],
  addToast: (message, type) => {
    const id = Math.random().toString(36).slice(2, 9);
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => get().removeToast(id), 4000);
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  getCaptionConfig: () => {
    const s = get();
    return { style: s.captionStyle, font_size: s.fontSize, text_color: s.textColor, position: s.position };
  },
  reset: () => set({
    step: 1, jobId: null, videoUrl: null, videoFilename: '', videoDuration: 0,
    segments: [], language: 'en', detectedLanguage: '',
    whisperModel: 'large-v3', transcribeLang: null, initialPrompt: '', hotwords: '',
    captionStyle: 'tiktok', fontSize: 'medium', textColor: '#FFFFFF', position: 'bottom',
    transcribeProgress: 0, exportProgress: 0, progressMessage: '', exportedVideoUrl: null,
  }),
}));
