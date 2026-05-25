import { useState, useEffect, useRef } from 'react';
import { useStore } from '../store';
import { exportVideo, getDownloadUrl, ProgressWebSocket } from '../api';
import { ProgressBar } from './ProgressBar';

export function ExportStep() {
  const { jobId, segments, setStep, addToast, reset, exportProgress, setExportProgress, progressMessage, setProgressMessage, exportedVideoUrl, setExportedVideoUrl, getCaptionConfig } = useStore();
  const [isExporting, setIsExporting] = useState(false);
  const wsRef = useRef<ProgressWebSocket | null>(null);
  useEffect(() => () => { wsRef.current?.disconnect(); }, []);

  const start = async () => {
    if (!jobId) return;
    setIsExporting(true); setExportProgress(0); setProgressMessage('Starting...');
    const ws = new ProgressWebSocket(jobId, (m) => { if (m.progress!==undefined) setExportProgress(m.progress); if (m.message) setProgressMessage(m.message); });
    ws.connect(); wsRef.current = ws;
    try {
      await exportVideo(jobId, segments, getCaptionConfig());
      setExportedVideoUrl(getDownloadUrl(jobId));
      addToast('Export complete!', 'success');
    } catch (e) { addToast(`Failed: ${(e as Error).message}`, 'error'); }
    finally { setIsExporting(false); ws.disconnect(); wsRef.current = null; setExportProgress(100); }
  };

  return (
    <div className="export-step">
      {!exportedVideoUrl && !isExporting && <div className="loading-center"><h3 style={{fontSize:'20px',marginBottom:'8px'}}>Ready to export 🎬</h3><p className="loading-text" style={{marginBottom:'16px'}}>FFmpeg will burn captions into your video.</p><button className="btn btn-primary btn-large" onClick={start} disabled={!jobId}>🔥 Export Video</button></div>}
      {isExporting && <div className="loading-center" style={{width:'100%'}}><div className="spinner spinner-lg"/><ProgressBar progress={exportProgress} message={progressMessage}/><p className="loading-text">Rendering...</p></div>}
      {exportedVideoUrl && <>
        <div className="export-video-container"><video src={exportedVideoUrl} controls playsInline style={{width:'100%',display:'block'}}/></div>
        <div style={{display:'flex',gap:'12px',flexWrap:'wrap',justifyContent:'center'}}>
          <a href={exportedVideoUrl} download className="btn btn-success btn-large">📥 Download Video</a>
          <button className="btn btn-secondary btn-large" onClick={reset}>🔄 Start Over</button>
        </div>
      </>}
      <div className="step-nav"><button className="btn btn-ghost" onClick={()=>setStep(3)}>← Back</button></div>
    </div>
  );
}
