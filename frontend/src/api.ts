import type { UploadResponse, TranscribeResponse, ExportResponse, TranscriptionSegment, CaptionConfig, WhisperModel, WSProgressMessage } from './types';

// In dev, route through Vite proxy (/api) to bypass CORS.
// In production builds, use the full VITE_API_URL.
const API_BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL
  : '/api';
const WS_BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/^http/, 'ws')
  : `ws://${window.location.host}/api`;

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const form = new FormData(); form.append('file', file);
  const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: 'Upload failed' })); throw new Error(e.detail); }
  return res.json();
}

export interface TranscribeParams {
  model: WhisperModel;
  language: string | null;
  initial_prompt: string | null;
  hotwords: string[];
}

export async function transcribeVideo(jobId: string, params: TranscribeParams): Promise<TranscribeResponse> {
  const body = {
    model: params.model,
    language: params.language || null,
    initial_prompt: params.initial_prompt || null,
    hotwords: params.hotwords.filter(w => w.trim()),
  };
  const res = await fetch(`${API_BASE}/transcribe/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: 'Transcription failed' })); throw new Error(e.detail); }
  return res.json();
}

export async function exportVideo(jobId: string, segments: TranscriptionSegment[], config: CaptionConfig): Promise<ExportResponse> {
  const res = await fetch(`${API_BASE}/export/${jobId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ segments, config }) });
  if (!res.ok) { const e = await res.json().catch(() => ({ detail: 'Export failed' })); throw new Error(e.detail); }
  return res.json();
}

export function getVideoUrl(jobId: string): string { return `${API_BASE}/video/${jobId}`; }
export function getDownloadUrl(jobId: string): string { return `${API_BASE}/download/${jobId}`; }

export class ProgressWebSocket {
  private ws: WebSocket | null = null;
  private jobId: string;
  private onMessage: (msg: WSProgressMessage) => void;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(jobId: string, onMessage: (msg: WSProgressMessage) => void) { this.jobId = jobId; this.onMessage = onMessage; }

  connect(): void {
    this.ws = new WebSocket(`${WS_BASE}/ws/${this.jobId}`);
    this.ws.onmessage = (e) => { try { this.onMessage(JSON.parse(e.data)); } catch {} };
    this.ws.onclose = () => { this.timer = setTimeout(() => { if (this.ws?.readyState === WebSocket.CLOSED) this.connect(); }, 2000); };
  }

  disconnect(): void {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    if (this.ws) { this.ws.close(); this.ws = null; }
  }
}
