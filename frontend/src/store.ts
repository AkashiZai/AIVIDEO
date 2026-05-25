// ===========================================================================
// Zustand Store — Global app state management
// ===========================================================================

import { create } from 'zustand';
import type {
  AppStep,
  CaptionStyleType,
  FontSize,
  CaptionPosition,
  CaptionConfig,
  TranscriptionSegment,
  Toast,
  WhisperModel,
} from './types';

interface AppStore {
  // Step navigation
  step: AppStep;
  setStep: (step: AppStep) => void;

  // Job
  jobId: string | null;
  setJobId: (id: string | null) => void;

  // Video
  videoUrl: string | null;
  setVideoUrl: (url: string | null) => void;
  videoFilename: string;
  setVideoFilename: (name: string) => void;
  videoDuration: number;
  setVideoDuration: (d: number) => void;

  // Transcription
  segments: TranscriptionSegment[];
  setSegments: (segs: TranscriptionSegment[]) => void;
  updateSegmentText: (id: number, text: string) => void;
  language: string;
  setLanguage: (lang: string) => void;

  // Whisper model
  whisperModel: WhisperModel;
  setWhisperModel: (model: WhisperModel) => void;

  // Caption styling
  captionStyle: CaptionStyleType;
  setCaptionStyle: (style: CaptionStyleType) => void;
  fontSize: FontSize;
  setFontSize: (size: FontSize) => void;
  textColor: string;
  setTextColor: (color: string) => void;
  position: CaptionPosition;
  setPosition: (pos: CaptionPosition) => void;

  // Progress
  transcribeProgress: number;
  setTranscribeProgress: (p: number) => void;
  exportProgress: number;
  setExportProgress: (p: number) => void;
  progressMessage: string;
  setProgressMessage: (msg: string) => void;

  // Export
  exportedVideoUrl: string | null;
  setExportedVideoUrl: (url: string | null) => void;

  // Toast notifications
  toasts: Toast[];
  addToast: (message: string, type: Toast['type']) => void;
  removeToast: (id: string) => void;

  // Computed
  getCaptionConfig: () => CaptionConfig;

  // Reset
  reset: () => void;
}

export const useStore = create<AppStore>((set, get) => ({
  // Step
  step: 1,
  setStep: (step) => set({ step }),

  // Job
  jobId: null,
  setJobId: (id) => set({ jobId: id }),

  // Video
  videoUrl: null,
  setVideoUrl: (url) => set({ videoUrl: url }),
  videoFilename: '',
  setVideoFilename: (name) => set({ videoFilename: name }),
  videoDuration: 0,
  setVideoDuration: (d) => set({ videoDuration: d }),

  // Transcription
  segments: [],
  setSegments: (segs) => set({ segments: segs }),
  updateSegmentText: (id, text) =>
    set((state) => ({
      segments: state.segments.map((s) =>
        s.id === id ? { ...s, text } : s
      ),
    })),
  language: 'en',
  setLanguage: (lang) => set({ language: lang }),

  // Whisper model
  whisperModel: 'base',
  setWhisperModel: (model) => set({ whisperModel: model }),

  // Caption styling
  captionStyle: 'tiktok',
  setCaptionStyle: (style) => set({ captionStyle: style }),
  fontSize: 'medium',
  setFontSize: (size) => set({ fontSize: size }),
  textColor: '#FFFFFF',
  setTextColor: (color) => set({ textColor: color }),
  position: 'bottom',
  setPosition: (pos) => set({ position: pos }),

  // Progress
  transcribeProgress: 0,
  setTranscribeProgress: (p) => set({ transcribeProgress: p }),
  exportProgress: 0,
  setExportProgress: (p) => set({ exportProgress: p }),
  progressMessage: '',
  setProgressMessage: (msg) => set({ progressMessage: msg }),

  // Export
  exportedVideoUrl: null,
  setExportedVideoUrl: (url) => set({ exportedVideoUrl: url }),

  // Toasts
  toasts: [],
  addToast: (message, type) => {
    const id = Math.random().toString(36).slice(2, 9);
    set((state) => ({
      toasts: [...state.toasts, { id, message, type }],
    }));
    setTimeout(() => get().removeToast(id), 4000);
  },
  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),

  // Computed
  getCaptionConfig: () => {
    const s = get();
    return {
      style: s.captionStyle,
      font_size: s.fontSize,
      text_color: s.textColor,
      position: s.position,
    };
  },

  // Reset
  reset: () =>
    set({
      step: 1,
      jobId: null,
      videoUrl: null,
      videoFilename: '',
      videoDuration: 0,
      segments: [],
      language: 'en',
      captionStyle: 'tiktok',
      fontSize: 'medium',
      textColor: '#FFFFFF',
      position: 'bottom',
      transcribeProgress: 0,
      exportProgress: 0,
      progressMessage: '',
      exportedVideoUrl: null,
    }),
}));
