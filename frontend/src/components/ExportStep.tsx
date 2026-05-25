// ===========================================================================
// ExportStep — Export, download, and preview final video
// ===========================================================================

import { useState, useEffect, useRef } from 'react';
import { useStore } from '../store';
import { exportVideo, getDownloadUrl, ProgressWebSocket } from '../api';
import { ProgressBar } from './ProgressBar';

export function ExportStep() {
  const {
    jobId, segments, setStep, addToast, reset,
    exportProgress, setExportProgress,
    progressMessage, setProgressMessage,
    exportedVideoUrl, setExportedVideoUrl,
    getCaptionConfig,
  } = useStore();

  const [isExporting, setIsExporting] = useState(false);
  const wsRef = useRef<ProgressWebSocket | null>(null);

  useEffect(() => {
    return () => {
      wsRef.current?.disconnect();
    };
  }, []);

  const startExport = async () => {
    if (!jobId) return;

    setIsExporting(true);
    setExportProgress(0);
    setProgressMessage('Starting export...');

    // WebSocket for progress
    const ws = new ProgressWebSocket(jobId, (msg) => {
      if (msg.progress !== undefined) setExportProgress(msg.progress);
      if (msg.message) setProgressMessage(msg.message);
    });
    ws.connect();
    wsRef.current = ws;

    try {
      const config = getCaptionConfig();
      await exportVideo(jobId, segments, config);
      setExportedVideoUrl(getDownloadUrl(jobId));
      addToast('Export complete! Your video is ready.', 'success');
    } catch (err) {
      addToast(`Export failed: ${(err as Error).message}`, 'error');
    } finally {
      setIsExporting(false);
      ws.disconnect();
      wsRef.current = null;
      setExportProgress(100);
    }
  };

  return (
    <div className="export-step">
      {/* Pre-export state */}
      {!exportedVideoUrl && !isExporting && (
        <div className="loading-center">
          <h3 style={{ fontSize: '20px', marginBottom: '8px' }}>Ready to export 🎬</h3>
          <p className="loading-text" style={{ marginBottom: '16px' }}>
            FFmpeg will burn captions into your video. This may take a few minutes.
          </p>
          <button
            className="btn btn-primary btn-large"
            onClick={startExport}
            disabled={!jobId}
            id="btn-start-export"
          >
            🔥 Export Video
          </button>
        </div>
      )}

      {/* Exporting progress */}
      {isExporting && (
        <div className="loading-center" style={{ width: '100%' }}>
          <div className="spinner spinner-lg" />
          <ProgressBar progress={exportProgress} message={progressMessage} />
          <p className="loading-text">FFmpeg is rendering your video with captions...</p>
        </div>
      )}

      {/* Export complete */}
      {exportedVideoUrl && (
        <>
          <div className="export-video-container" id="export-video">
            <video
              src={exportedVideoUrl}
              controls
              playsInline
              style={{ width: '100%', display: 'block' }}
            />
          </div>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center' }}>
            <a
              href={exportedVideoUrl}
              download
              className="btn btn-success btn-large"
              id="btn-download"
            >
              📥 Download Video
            </a>
            <button
              className="btn btn-secondary btn-large"
              onClick={() => {
                reset();
              }}
              id="btn-start-over"
            >
              🔄 Start Over
            </button>
          </div>
        </>
      )}

      {/* Navigation */}
      <div className="step-nav">
        <button className="btn btn-ghost" onClick={() => setStep(3)} id="btn-back-style">
          ← Back
        </button>
      </div>
    </div>
  );
}
