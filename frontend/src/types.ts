// ===========================================================================
// TypeScript types for the AI Auto-Caption Video Editor frontend
// ===========================================================================

// ---------------------------------------------------------------------------
// Caption & Transcription Types
// ---------------------------------------------------------------------------

export interface WordTimestamp {
  word: string;
  start: number;
  end: number;
  confidence: number;
}

export interface TranscriptionSegment {
  id: number;
  text: string;
  start: number;
  end: number;
  words: WordTimestamp[];
}

export interface TranscriptionResult {
  segments: TranscriptionSegment[];
  language: string;
  duration: number;
}

// ---------------------------------------------------------------------------
// Caption Styling
// ---------------------------------------------------------------------------

export type CaptionStyleType = 'tiktok' | 'subtitle' | 'word_by_word' | 'karaoke';
export type FontSize = 'small' | 'medium' | 'large';
export type CaptionPosition = 'top' | 'center' | 'bottom';
export type WhisperModel = 'base' | 'small' | 'medium';

export interface CaptionConfig {
  style: CaptionStyleType;
  font_size: FontSize;
  text_color: string;
  position: CaptionPosition;
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

// ---------------------------------------------------------------------------
// Job & API Types
// ---------------------------------------------------------------------------

export type JobStatus =
  | 'pending'
  | 'transcribing'
  | 'transcribed'
  | 'exporting'
  | 'completed'
  | 'error';

export interface UploadResponse {
  job_id: string;
  filename: string;
  duration: number;
  message: string;
}

export interface StatusResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  download_url: string | null;
  error: string | null;
}

export interface TranscribeResponse {
  job_id: string;
  segments: TranscriptionSegment[];
  language: string;
  duration: number;
}

export interface ExportResponse {
  job_id: string;
  message: string;
}

// ---------------------------------------------------------------------------
// WebSocket Messages
// ---------------------------------------------------------------------------

export interface WSProgressMessage {
  type: 'progress' | 'status' | 'error' | 'pong';
  job_id?: string;
  status?: string;
  progress?: number;
  message?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// App Step
// ---------------------------------------------------------------------------

export type AppStep = 1 | 2 | 3 | 4;

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
}
