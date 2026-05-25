// ===========================================================================
// TranscribeStep — Whisper transcription with editable results
// ===========================================================================

import { useState, useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store';
import { transcribeVideo, ProgressWebSocket } from '../api';
import { ProgressBar } from './ProgressBar';
import type { WhisperModel } from '../types';

export function TranscribeStep() {
  const {
    jobId, segments, setSegments, setLanguage, setStep,
    whisperModel, setWhisperModel, updateSegmentText, addToast,
    transcribeProgress, setTranscribeProgress, progressMessage, setProgressMessage,
  } = useStore();

  const [isTranscribing, setIsTranscribing] = useState(false);
  const [hasTranscribed, setHasTranscribed] = useState(segments.length > 0);
  const wsRef = useRef<ProgressWebSocket | null>(null);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.disconnect();
    };
  }, []);

  const startTranscription = useCallback(async () => {
    if (!jobId) return;

    setIsTranscribing(true);
    setTranscribeProgress(0);
    setProgressMessage('Starting transcription...');

    // Connect WebSocket for progress
    const ws = new ProgressWebSocket(jobId, (msg) => {
      if (msg.progress !== undefined) {
        setTranscribeProgress(msg.progress);
      }
      if (msg.message) {
        setProgressMessage(msg.message);
      }
    });
    ws.connect();
    wsRef.current = ws;

    try {
      const result = await transcribeVideo(jobId, whisperModel);
      setSegments(result.segments);
      setLanguage(result.language);
      setHasTranscribed(true);
      addToast(`Transcription complete! (${result.language.toUpperCase()})`, 'success');
    } catch (err) {
      addToast(`Transcription failed: ${(err as Error).message}`, 'error');
    } finally {
      setIsTranscribing(false);
      ws.disconnect();
      wsRef.current = null;
      setTranscribeProgress(100);
    }
  }, [jobId, whisperModel, setSegments, setLanguage, setTranscribeProgress, setProgressMessage, addToast]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    const ms = Math.floor((s % 1) * 10);
    return `${m}:${sec.toString().padStart(2, '0')}.${ms}`;
  };

  return (
    <div className="transcribe-step">
      {/* Model selector */}
      <div className="model-selector" id="model-selector">
        <label htmlFor="whisper-model">Whisper Model:</label>
        <select
          id="whisper-model"
          value={whisperModel}
          onChange={(e) => setWhisperModel(e.target.value as WhisperModel)}
          disabled={isTranscribing}
        >
          <option value="base">Base (fastest, ~1GB)</option>
          <option value="small">Small (balanced, ~2GB)</option>
          <option value="medium">Medium (best quality, ~5GB)</option>
        </select>
      </div>

      {/* Transcribe button or progress */}
      {!hasTranscribed && !isTranscribing && (
        <div className="loading-center">
          <button
            className="btn btn-primary btn-large"
            onClick={startTranscription}
            disabled={!jobId}
            id="btn-start-transcribe"
          >
            🧠 Start Transcription
          </button>
          <p className="loading-text">This may take a moment depending on the video length and model size.</p>
        </div>
      )}

      {isTranscribing && (
        <div className="loading-center">
          <div className="spinner spinner-lg" />
          <ProgressBar progress={transcribeProgress} message={progressMessage} />
        </div>
      )}

      {/* Editable transcript */}
      {hasTranscribed && segments.length > 0 && (
        <div className="transcript-editor" id="transcript-editor">
          <h3 style={{ marginBottom: '12px', fontSize: '16px', color: 'var(--text-secondary)' }}>
            ✏️ Edit Transcript ({segments.length} segments)
          </h3>
          {segments.map((seg) => (
            <div className="transcript-segment" key={seg.id}>
              <span className="segment-time">
                {formatTime(seg.start)} – {formatTime(seg.end)}
              </span>
              <textarea
                className="segment-text"
                value={seg.text}
                onChange={(e) => updateSegmentText(seg.id, e.target.value)}
                rows={1}
              />
            </div>
          ))}
        </div>
      )}

      {/* Navigation */}
      <div className="step-nav">
        <button className="btn btn-ghost" onClick={() => setStep(1)} id="btn-back-upload">
          ← Back
        </button>
        {hasTranscribed && (
          <button
            className="btn btn-primary btn-large"
            onClick={() => setStep(3)}
            id="btn-next-style"
          >
            Next: Choose Style →
          </button>
        )}
      </div>
    </div>
  );
}
