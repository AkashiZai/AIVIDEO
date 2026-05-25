// ===========================================================================
// App.tsx — Main application shell with step-based routing
// ===========================================================================

import { useStore } from './store';
import { StepIndicator } from './components/StepIndicator';
import { UploadStep } from './components/UploadStep';
import { TranscribeStep } from './components/TranscribeStep';
import { StyleStep } from './components/StyleStep';
import { ExportStep } from './components/ExportStep';
import { ToastContainer } from './components/Toast';

export default function App() {
  const step = useStore((s) => s.step);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-logo">
          <span className="app-logo-icon">🎬</span>
          <h1>CaptionForge AI</h1>
        </div>
        <span className="app-badge">Powered by Whisper</span>
      </header>

      <StepIndicator />

      <main className="app-content">
        {step === 1 && <UploadStep />}
        {step === 2 && <TranscribeStep />}
        {step === 3 && <StyleStep />}
        {step === 4 && <ExportStep />}
      </main>

      <ToastContainer />
    </div>
  );
}
