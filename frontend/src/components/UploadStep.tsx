// ===========================================================================
// UploadStep — Video upload with drag & drop
// ===========================================================================

import { useState, useRef, useCallback } from 'react';
import { useStore } from '../store';
import { uploadVideo, getVideoUrl } from '../api';

export function UploadStep() {
  const { setJobId, setVideoUrl, setVideoFilename, setVideoDuration, setStep, addToast } =
    useStore();
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState('');
  const [duration, setDuration] = useState(0);
  const [uploaded, setUploaded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    if (isUploading) return;

    setIsUploading(true);
    setFileName(file.name);

    try {
      const result = await uploadVideo(file);
      setJobId(result.job_id);
      const url = getVideoUrl(result.job_id);
      setVideoUrl(url);
      setVideoFilename(result.filename);
      setVideoDuration(result.duration);
      setPreviewUrl(url);
      setDuration(result.duration);
      setUploaded(true);
      addToast('Video uploaded successfully!', 'success');
    } catch (err) {
      addToast(`Upload failed: ${(err as Error).message}`, 'error');
    } finally {
      setIsUploading(false);
    }
  }, [isUploading, setJobId, setVideoUrl, setVideoFilename, setVideoDuration, addToast]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const formatDuration = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div className="upload-step">
      {!uploaded ? (
        <div
          id="upload-drop-zone"
          className={`upload-drop-zone ${isDragOver ? 'drag-over' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDragEnter={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragOver(false); }}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter') fileInputRef.current?.click(); }}
        >
          {isUploading ? (
            <div className="loading-center">
              <div className="spinner spinner-lg" />
              <p className="loading-text">Uploading {fileName}...</p>
            </div>
          ) : (
            <>
              <div className="upload-icon">🎥</div>
              <h2 className="upload-title">Drop your video here</h2>
              <p className="upload-subtitle">or click to browse files</p>
              <div className="upload-formats">
                {['MP4', 'MOV', 'AVI', 'MKV', 'WebM', 'MP3', 'WAV'].map((f) => (
                  <span key={f}>{f}</span>
                ))}
              </div>
            </>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept="video/*,audio/*"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
            id="file-input"
          />
        </div>
      ) : (
        <div className="upload-preview" id="upload-preview">
          <video
            src={previewUrl || undefined}
            controls
            playsInline
          />
          <div className="upload-preview-info">
            <span className="upload-preview-name">{fileName}</span>
            <span className="upload-preview-duration">{formatDuration(duration)}</span>
          </div>
        </div>
      )}

      {uploaded && (
        <div className="step-nav">
          <div />
          <button
            className="btn btn-primary btn-large"
            onClick={() => setStep(2)}
            id="btn-next-transcribe"
          >
            Next: Transcribe →
          </button>
        </div>
      )}
    </div>
  );
}
