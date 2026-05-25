import { useState, useRef, useCallback } from 'react';
import { useStore } from '../store';
import { uploadVideo, getVideoUrl } from '../api';

export function UploadStep() {
  const { setJobId, setVideoUrl, setVideoFilename, setVideoDuration, setStep, addToast } = useStore();
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState('');
  const [duration, setDuration] = useState(0);
  const [uploaded, setUploaded] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    if (isUploading) return;
    setIsUploading(true); setFileName(file.name);
    try {
      const r = await uploadVideo(file);
      setJobId(r.job_id); const url = getVideoUrl(r.job_id);
      setVideoUrl(url); setVideoFilename(r.filename); setVideoDuration(r.duration);
      setPreviewUrl(url); setDuration(r.duration); setUploaded(true);
      addToast('Video uploaded!', 'success');
    } catch (e) { addToast(`Upload failed: ${(e as Error).message}`, 'error'); }
    finally { setIsUploading(false); }
  }, [isUploading, setJobId, setVideoUrl, setVideoFilename, setVideoDuration, addToast]);

  const fmt = (s: number) => `${Math.floor(s/60)}:${Math.floor(s%60).toString().padStart(2,'0')}`;

  return (
    <div className="upload-step">
      {!uploaded ? (
        <div className={`upload-drop-zone ${isDragOver?'drag-over':''}`} onClick={() => inputRef.current?.click()}
          onDragEnter={(e)=>{e.preventDefault();setIsDragOver(true)}} onDragOver={(e)=>{e.preventDefault();setIsDragOver(true)}}
          onDragLeave={(e)=>{e.preventDefault();setIsDragOver(false)}}
          onDrop={(e)=>{e.preventDefault();setIsDragOver(false);const f=e.dataTransfer.files[0];if(f)handleFile(f)}}
          role="button" tabIndex={0}>
          {isUploading ? (<div className="loading-center"><div className="spinner spinner-lg"/><p className="loading-text">Uploading {fileName}...</p></div>) : (<>
            <div className="upload-icon">🎥</div><h2 className="upload-title">Drop your video here</h2>
            <p className="upload-subtitle">or click to browse files</p>
            <div className="upload-formats">{['MP4','MOV','AVI','MKV','WebM','MP3','WAV'].map(f=><span key={f}>{f}</span>)}</div></>)}
          <input ref={inputRef} type="file" accept="video/*,audio/*" style={{display:'none'}} onChange={(e)=>{const f=e.target.files?.[0];if(f)handleFile(f)}}/>
        </div>
      ) : (
        <div className="upload-preview"><video src={previewUrl||undefined} controls playsInline/>
          <div className="upload-preview-info"><span className="upload-preview-name">{fileName}</span><span className="upload-preview-duration">{fmt(duration)}</span></div></div>
      )}
      {uploaded && <div className="step-nav"><div/><button className="btn btn-primary btn-large" onClick={() => setStep(2)}>Next: Transcribe →</button></div>}
    </div>
  );
}
