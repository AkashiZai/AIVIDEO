import { useStore } from '../store';
const STEPS = [{num:1,label:'Upload'},{num:2,label:'Transcribe'},{num:3,label:'Style'},{num:4,label:'Export'}] as const;
export function StepIndicator() {
  const step = useStore((s) => s.step);
  return (<div className="step-indicator" id="step-indicator">{STEPS.map((s,i) => (<div key={s.num} style={{display:'flex',alignItems:'center'}}><div className={`step-item ${step===s.num?'active':''} ${step>s.num?'completed':''}`}><div className="step-circle">{step>s.num?'✓':s.num}</div><span className="step-label">{s.label}</span></div>{i<STEPS.length-1&&<div className={`step-line ${step>s.num?'completed':''}`}/>}</div>))}</div>);
}
