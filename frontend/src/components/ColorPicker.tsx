// ===========================================================================
// ColorPicker — Preset color swatches + custom color input
// ===========================================================================

const PRESETS = ['#FFFFFF', '#FFD700', '#FF4444', '#00FF88', '#00BFFF', '#FF69B4'];

interface ColorPickerProps {
  value: string;
  onChange: (color: string) => void;
}

export function ColorPicker({ value, onChange }: ColorPickerProps) {
  const normalized = value.toUpperCase();

  return (
    <div className="color-picker" id="color-picker">
      {PRESETS.map((c) => (
        <button
          key={c}
          className={`color-swatch ${normalized === c ? 'active' : ''}`}
          style={{ backgroundColor: c }}
          onClick={() => onChange(c)}
          aria-label={`Color ${c}`}
          type="button"
        />
      ))}
      <input
        type="color"
        className="color-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Custom color"
      />
    </div>
  );
}
