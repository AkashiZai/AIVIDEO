interface Props { progress: number; message?: string; }
export function ProgressBar({ progress, message }: Props) {
  const p = Math.min(100, Math.max(0, progress));
  return (<div className="progress-bar-wrapper"><div className="progress-bar"><div className={`progress-fill ${p>0&&p<100?'pulse':''}`} style={{width:`${p}%`}}/></div><div className="progress-info"><span className="progress-message">{message||''}</span><span className="progress-percent">{Math.round(p)}%</span></div></div>);
}
