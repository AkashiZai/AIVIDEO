const PRESETS = ['#FFFFFF','#FFD700','#FF4444','#00FF88','#00BFFF','#FF69B4'];
interface Props { value: string; onChange: (c: string) => void; }
export function ColorPicker({ value, onChange }: Props) {
  const n = value.toUpperCase();
  return (<div className="color-picker">{PRESETS.map((c) => (<button key={c} className={`color-swatch ${n===c?'active':''}`} style={{backgroundColor:c}} onClick={() => onChange(c)} type="button"/>))}<input type="color" className="color-input" value={value} onChange={(e) => onChange(e.target.value)}/></div>);
}
