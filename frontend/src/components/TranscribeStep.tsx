import { useState, useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store';
import { transcribeVideo, ProgressWebSocket } from '../api';
import { ProgressBar } from './ProgressBar';
import { WHISPER_MODELS, LANGUAGES } from '../types';
import type { WhisperModel } from '../types';

function confidenceClass(c: number): string {
  if (c >= 0.85) return 'conf-high';
  if (c >= 0.6) return 'conf-medium';
  return 'conf-low';
}

// Presets for common use cases
const PRESETS = [
  {
    id: 'thai-song',
    label: '🎵 เพลงไทย (แม่นสุด)',
    desc: 'AI ฟังเพลง → Whisper จับเวลา → Merge (3-pass pipeline)',
    model: 'large-v3' as WhisperModel,
    lang: 'th',
    prompt: 'เพลงไทย เนื้อเพลงภาษาไทย ร้องเพลง',
    hotwords: 'รัก,หัวใจ,ชอบ,เธอ,เท่าไหร่,สะออน,คิดถึง,ร้องไห้,กลัว,กว่า,สาย,ชีวิต',
  },
  {
    id: 'thai-song-fast',
    label: '🎵 เพลงไทย (เร็ว)',
    desc: 'ใช้ Medium สำหรับเนื้อเพลงไทย — เร็วกว่า แต่แม่นน้อยกว่า',
    model: 'medium' as WhisperModel,
    lang: 'th',
    prompt: 'เพลงไทย เนื้อเพลงภาษาไทย ร้องเพลง',
    hotwords: 'รัก,หัวใจ,ชอบ,เธอ,เท่าไหร่,สะออน',
  },
  {
    id: 'thai-speech',
    label: '🗣️ พูดไทย',
    desc: 'ใช้ Large-v3 สำหรับคนพูดไทยทั่วไป',
    model: 'large-v3' as WhisperModel,
    lang: 'th',
    prompt: 'การพูดภาษาไทย บทสนทนาภาษาไทย',
    hotwords: '',
  },
  {
    id: 'en-default',
    label: '🇬🇧 English',
    desc: 'Default English speech',
    model: 'base' as WhisperModel,
    lang: 'en',
    prompt: '',
    hotwords: '',
  },
] as const;

export function TranscribeStep() {
  const {
    jobId, segments, setSegments, setLanguage, setDetectedLanguage, setStep,
    whisperModel, setWhisperModel,
    transcribeLang, setTranscribeLang,
    initialPrompt, setInitialPrompt,
    hotwords, setHotwords,
    updateSegmentText, addToast,
    transcribeProgress, setTranscribeProgress,
    progressMessage, setProgressMessage,
  } = useStore();

  const [isTranscribing, setIsTranscribing] = useState(false);
  const [hasTranscribed, setHasTranscribed] = useState(segments.length > 0);
  const [showSettings, setShowSettings] = useState(true);
  const [editingSegment, setEditingSegment] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');
  const editRef = useRef<HTMLInputElement>(null);
  const wsRef = useRef<ProgressWebSocket | null>(null);

  useEffect(() => () => { wsRef.current?.disconnect(); }, []);

  // Focus the edit input when a sentence is clicked
  useEffect(() => {
    if (editingSegment !== null && editRef.current) editRef.current.focus();
  }, [editingSegment]);

  const start = useCallback(async () => {
    if (!jobId) return;
    setIsTranscribing(true); setTranscribeProgress(0); setProgressMessage('Starting...');

    const ws = new ProgressWebSocket(jobId, (m) => {
      if (m.progress !== undefined) setTranscribeProgress(m.progress);
      if (m.message) setProgressMessage(m.message);
    });
    ws.connect(); wsRef.current = ws;

    try {
      const hwList = hotwords.split(',').map(w => w.trim()).filter(Boolean);
      const r = await transcribeVideo(jobId, {
        model: whisperModel,
        language: transcribeLang,
        initial_prompt: initialPrompt || null,
        hotwords: hwList,
      });
      setSegments(r.segments);
      setLanguage(r.language);
      setDetectedLanguage(r.language);
      setHasTranscribed(true);
      setShowSettings(false);
      addToast(`Transcription complete! Language: ${r.language.toUpperCase()}`, 'success');
    } catch (e) {
      addToast(`Failed: ${(e as Error).message}`, 'error');
    } finally {
      setIsTranscribing(false);
      ws.disconnect(); wsRef.current = null;
      setTranscribeProgress(100);
    }
  }, [jobId, whisperModel, transcribeLang, initialPrompt, hotwords, setSegments, setLanguage, setDetectedLanguage, setTranscribeProgress, setProgressMessage, addToast]);

  const applyPreset = (presetId: string) => {
    const preset = PRESETS.find(p => p.id === presetId);
    if (!preset) return;
    setWhisperModel(preset.model);
    setTranscribeLang(preset.lang);
    setInitialPrompt(preset.prompt);
    setHotwords(preset.hotwords);
    addToast(`Preset applied: ${preset.label}`, 'info');
  };

  const handleSentenceClick = (segId: number, text: string) => {
    setEditingSegment(segId);
    setEditValue(text);
  };

  const commitEdit = () => {
    if (editingSegment !== null && editValue.trim()) {
      updateSegmentText(editingSegment, editValue.trim());
    }
    setEditingSegment(null);
    setEditValue('');
  };

  const fmt = (s: number) => `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}.${Math.floor((s % 1) * 10)}`;

  return (
    <div className="transcribe-step">

      {/* Transcription Settings Panel */}
      <div className="settings-panel">
        <button className="settings-toggle" onClick={() => setShowSettings(!showSettings)} type="button">
          ⚙️ Transcription Settings {showSettings ? '▼' : '▶'}
        </button>

        {showSettings && (
          <div className="settings-body">
            {/* Presets Row */}
            <div className="settings-field">
              <label>Quick Presets <span className="label-hint">(auto-configure for best accuracy)</span></label>
              <div className="preset-buttons">
                {PRESETS.map(p => (
                  <button
                    key={p.id}
                    className={`btn btn-preset ${
                      whisperModel === p.model && transcribeLang === p.lang ? 'btn-preset-active' : ''
                    }`}
                    onClick={() => applyPreset(p.id)}
                    disabled={isTranscribing}
                    title={p.desc}
                    type="button"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Row 1: Model + Language */}
            <div className="settings-row">
              <div className="settings-field">
                <label htmlFor="wm">Accuracy Mode</label>
                <select id="wm" value={whisperModel} onChange={(e) => setWhisperModel(e.target.value as WhisperModel)} disabled={isTranscribing}>
                  {WHISPER_MODELS.map(m => (
                    <option key={m.value} value={m.value}>{m.label} — {m.desc}</option>
                  ))}
                </select>
              </div>

              <div className="settings-field">
                <label htmlFor="lang">Language</label>
                <select id="lang" value={transcribeLang ?? ''} onChange={(e) => setTranscribeLang(e.target.value || null)} disabled={isTranscribing}>
                  {LANGUAGES.map(l => (
                    <option key={l.code ?? 'auto'} value={l.code ?? ''}>{l.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Row 2: Context hint */}
            <div className="settings-field">
              <label htmlFor="prompt">Context Hint <span className="label-hint">(helps accuracy for jargon/names)</span></label>
              <input
                id="prompt"
                type="text"
                className="settings-input"
                placeholder='e.g. "This is a cooking video about Thai food"'
                value={initialPrompt}
                onChange={(e) => setInitialPrompt(e.target.value)}
                disabled={isTranscribing}
              />
            </div>

            {/* Row 3: Hotwords */}
            <div className="settings-field">
              <label htmlFor="hw">Hotwords <span className="label-hint">(comma-separated, boosts recognition)</span></label>
              <input
                id="hw"
                type="text"
                className="settings-input"
                placeholder="e.g. CaptionForge, Whisper, FFmpeg"
                value={hotwords}
                onChange={(e) => setHotwords(e.target.value)}
                disabled={isTranscribing}
              />
            </div>

            {/* Info badges */}
            <div className="settings-badges">
              <span className="badge badge-accent">faster-whisper</span>
              <span className="badge badge-accent">VAD filter</span>
              <span className="badge badge-accent">{transcribeLang === 'th' ? 'beam=10 (TH)' : 'beam=5'}</span>
              <span className="badge badge-accent">word timestamps</span>
              {transcribeLang === 'th' && (
                <>
                  <span className="badge badge-success">🔍 Lyrics Search</span>
                  <span className="badge badge-success">🤖 AI Correction</span>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Transcribe button or progress */}
      {!hasTranscribed && !isTranscribing && (
        <div className="loading-center">
          <button className="btn btn-primary btn-large" onClick={start} disabled={!jobId}>
            🧠 Start Transcription
          </button>
          <p className="loading-text">
            Using <strong>{WHISPER_MODELS.find(m => m.value === whisperModel)?.label}</strong> model
            {transcribeLang ? ` • ${LANGUAGES.find(l => l.code === transcribeLang)?.label}` : ' • Auto-detect language'}
          </p>
        </div>
      )}

      {isTranscribing && (
        <div className="loading-center">
          <div className="spinner spinner-lg" />
          <ProgressBar progress={transcribeProgress} message={progressMessage} />
        </div>
      )}

      {/* Word-level transcript editor with confidence colors */}
      {hasTranscribed && segments.length > 0 && (
        <div className="transcript-editor" id="transcript-editor">
          <div className="transcript-header">
            <h3>✏️ Word-Level Transcript ({segments.length} segments)</h3>
            <div className="confidence-legend">
              <span className="legend-item"><span className="legend-dot conf-high" />High</span>
              <span className="legend-item"><span className="legend-dot conf-medium" />Medium</span>
              <span className="legend-item"><span className="legend-dot conf-low" />Low</span>
            </div>
          </div>

          {segments.map((seg) => {
            const isEditing = editingSegment === seg.id;
            return (
              <div className="transcript-segment" key={seg.id}>
                <span className="segment-time">{fmt(seg.start)} – {fmt(seg.end)}</span>
                <div className="segment-sentence" onClick={() => !isEditing && handleSentenceClick(seg.id, seg.text)}>
                  {isEditing ? (
                    <input
                      ref={editRef}
                      className="sentence-edit-input"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={commitEdit}
                      onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') { setEditingSegment(null); setEditValue(''); } }}
                    />
                  ) : (
                    seg.words.length > 0 ? seg.words.map((w, i) => (
                      <span
                        key={i}
                        className={`word-inline ${confidenceClass(w.confidence)}`}
                        title={`confidence: ${(w.confidence * 100).toFixed(0)}% — click sentence to edit`}
                      >{w.word}</span>
                    )) : (
                      <span className="segment-text-plain">{seg.text}</span>
                    )
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {hasTranscribed && segments.length === 0 && (
        <div className="loading-center">
          <div className="upload-icon">🔇</div>
          <p className="loading-text" style={{ fontSize: '16px', color: 'var(--text-primary)' }}>No speech was detected in this video.</p>
          <p className="loading-text">This could mean the video has no audio, or the speech is too quiet/unclear.</p>
          <button className="btn btn-secondary" onClick={() => { setHasTranscribed(false); setShowSettings(true); }} style={{ marginTop: '16px' }}>
            Try Again with Different Settings
          </button>
        </div>
      )}

      {/* Navigation */}
      <div className="step-nav">
        <button className="btn btn-ghost" onClick={() => setStep(1)}>← Back</button>
        {hasTranscribed && (
          <button className="btn btn-primary btn-large" onClick={() => setStep(3)}>
            Next: Choose Style →
          </button>
        )}
      </div>
    </div>
  );
}
