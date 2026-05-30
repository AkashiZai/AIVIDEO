export interface WordTimestamp { word: string; start: number; end: number; confidence: number; }
export interface TranscriptionSegment { id: number; text: string; start: number; end: number; words: WordTimestamp[]; }
export interface TranscriptionResult { segments: TranscriptionSegment[]; language: string; duration: number; }

export type CaptionStyleType = 'tiktok' | 'subtitle' | 'word_by_word' | 'karaoke';
export type FontSize = 'small' | 'medium' | 'large';
export type CaptionPosition = 'top' | 'center' | 'bottom';
export type ASRModel = 'typhoon-asr-realtime' | 'typhoon-isan-asr-realtime';
export type AppStep = 1 | 2 | 3 | 4;
export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface CaptionConfig { style: CaptionStyleType; font_size: FontSize; text_color: string; position: CaptionPosition; }

export interface TranscribeSettings {
  model: ASRModel;
  language: string | null;     // null = auto-detect
  initial_prompt: string;      // context hint
  hotwords: string;            // comma-separated
}

export const CAPTION_STYLES: { value: CaptionStyleType; label: string; description: string; icon: string }[] = [
  { value: 'tiktok', label: 'TikTok', description: 'Bold word-by-word, center screen', icon: '🔥' },
  { value: 'subtitle', label: 'Subtitle', description: 'Classic bottom subtitles with bar', icon: '📺' },
  { value: 'word_by_word', label: 'Word-by-Word', description: 'Words build up, then clear', icon: '✍️' },
  { value: 'karaoke', label: 'Karaoke', description: 'Full line, active word highlighted', icon: '🎤' },
];

export const FONT_SIZES: { value: FontSize; label: string; px: number }[] = [
  { value: 'small', label: 'Small', px: 28 },
  { value: 'medium', label: 'Medium', px: 42 },
  { value: 'large', label: 'Large', px: 60 },
];

export const ASR_MODELS: { value: ASRModel; label: string; desc: string }[] = [
  { value: 'typhoon-asr-realtime', label: 'Typhoon ASR', desc: 'Fast and accurate for general Thai speech' },
  { value: 'typhoon-isan-asr-realtime', label: 'Typhoon Isan ASR', desc: 'Specialized for Isan dialect and general Thai' },
];

export const LANGUAGES: { code: string | null; label: string }[] = [
  { code: null, label: '🌍 Auto-detect' },
  { code: 'en', label: '🇬🇧 English' },
  { code: 'th', label: '🇹🇭 Thai' },
  { code: 'ja', label: '🇯🇵 Japanese' },
  { code: 'ko', label: '🇰🇷 Korean' },
  { code: 'zh', label: '🇨🇳 Chinese' },
  { code: 'es', label: '🇪🇸 Spanish' },
  { code: 'fr', label: '🇫🇷 French' },
  { code: 'de', label: '🇩🇪 German' },
  { code: 'pt', label: '🇧🇷 Portuguese' },
  { code: 'ru', label: '🇷🇺 Russian' },
  { code: 'ar', label: '🇸🇦 Arabic' },
  { code: 'hi', label: '🇮🇳 Hindi' },
  { code: 'id', label: '🇮🇩 Indonesian' },
  { code: 'vi', label: '🇻🇳 Vietnamese' },
];

export interface Toast { id: string; message: string; type: ToastType; }

export interface UploadResponse { job_id: string; filename: string; duration: number; message: string; }
export interface StatusResponse { job_id: string; status: string; progress: number; message: string; download_url: string | null; error: string | null; }
export interface TranscribeResponse { job_id: string; segments: TranscriptionSegment[]; language: string; duration: number; }
export interface ExportResponse { job_id: string; message: string; }
export interface WSProgressMessage { type: 'progress' | 'status' | 'error' | 'pong'; job_id?: string; status?: string; progress?: number; message?: string; error?: string; }
