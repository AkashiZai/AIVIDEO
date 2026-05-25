// ===========================================================================
// ProgressBar — Animated progress with message
// ===========================================================================

interface ProgressBarProps {
  progress: number;
  message?: string;
}

export function ProgressBar({ progress, message }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, progress));
  const isPulsing = pct > 0 && pct < 100;

  return (
    <div className="progress-bar-wrapper" id="progress-bar">
      <div className="progress-bar">
        <div
          className={`progress-fill ${isPulsing ? 'pulse' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="progress-info">
        <span className="progress-message">{message || ''}</span>
        <span className="progress-percent">{Math.round(pct)}%</span>
      </div>
    </div>
  );
}
