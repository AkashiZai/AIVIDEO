// ===========================================================================
// Toast — Toast notification container
// ===========================================================================

import { useStore } from '../store';

const TOAST_ICONS: Record<string, string> = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
};

export function ToastContainer() {
  const toasts = useStore((s) => s.toasts);

  return (
    <div className="toast-container" id="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          <span className="toast-icon">{TOAST_ICONS[t.type]}</span>
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
