// ===========================================================================
// API Client — REST + WebSocket communication with the backend
// ===========================================================================

import type {
  UploadResponse,
  TranscribeResponse,
  ExportResponse,
  StatusResponse,
  TranscriptionSegment,
  CaptionConfig,
  WhisperModel,
  WSProgressMessage,
} from './types';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = API_BASE.replace(/^http/, 'ws');

// ---------------------------------------------------------------------------
// REST API
// ---------------------------------------------------------------------------

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }

  return res.json();
}

export async function transcribeVideo(
  jobId: string,
  model: WhisperModel = 'base',
): Promise<TranscribeResponse> {
  const res = await fetch(`${API_BASE}/transcribe/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Transcription failed' }));
    throw new Error(err.detail || 'Transcription failed');
  }

  return res.json();
}

export async function exportVideo(
  jobId: string,
  segments: TranscriptionSegment[],
  config: CaptionConfig,
): Promise<ExportResponse> {
  const res = await fetch(`${API_BASE}/export/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ segments, config }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Export failed' }));
    throw new Error(err.detail || 'Export failed');
  }

  return res.json();
}

export async function getJobStatus(jobId: string): Promise<StatusResponse> {
  const res = await fetch(`${API_BASE}/status/${jobId}`);

  if (!res.ok) {
    throw new Error('Failed to get job status');
  }

  return res.json();
}

export function getVideoUrl(jobId: string): string {
  return `${API_BASE}/video/${jobId}`;
}

export function getDownloadUrl(jobId: string): string {
  return `${API_BASE}/download/${jobId}`;
}

// ---------------------------------------------------------------------------
// WebSocket Client
// ---------------------------------------------------------------------------

export class ProgressWebSocket {
  private ws: WebSocket | null = null;
  private jobId: string;
  private onMessage: (msg: WSProgressMessage) => void;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(jobId: string, onMessage: (msg: WSProgressMessage) => void) {
    this.jobId = jobId;
    this.onMessage = onMessage;
  }

  connect(): void {
    if (this.ws) {
      this.ws.close();
    }

    this.ws = new WebSocket(`${WS_BASE}/ws/${this.jobId}`);

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSProgressMessage;
        this.onMessage(data);
      } catch {
        // Ignore invalid messages
      }
    };

    this.ws.onclose = () => {
      // Reconnect after 2 seconds if not intentionally closed
      this.reconnectTimer = setTimeout(() => {
        if (this.ws?.readyState === WebSocket.CLOSED) {
          this.connect();
        }
      }, 2000);
    };

    this.ws.onerror = () => {
      // Error will trigger onclose
    };
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  ping(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping');
    }
  }
}
