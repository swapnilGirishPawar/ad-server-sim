import React from 'react'

export const cls = (...a) => a.filter(Boolean).join(' ')

export function Card({ title, right, children, className }) {
  return (
    <div className={cls(
      'rounded-2xl border border-line bg-gradient-to-b from-panel-raised to-panel p-5 shadow-card',
      className
    )}>
      {(title || right) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h3 className="text-[13px] font-bold tracking-tight text-slate-100">{title}</h3>}
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

export function Stat({ label, value, sub, tone }) {
  const toneCls = { good: 'text-emerald-400', warn: 'text-amber-400', bad: 'text-rose-400' }[tone] || 'text-slate-100'
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <div className="text-[10.5px] font-bold uppercase tracking-wider text-slate-500">{label}</div>
      <div className={cls('mt-1.5 text-[21px] font-bold leading-none tracking-tight tabular-nums', toneCls)}>{value}</div>
      {sub != null && <div className="mt-1.5 text-[11px] text-slate-500">{sub}</div>}
    </div>
  )
}

const VERDICT = {
  PASS: 'bg-emerald-500/15 text-emerald-300 border-emerald-600/40',
  GAP: 'bg-amber-500/15 text-amber-300 border-amber-600/40',
  FAIL: 'bg-rose-500/15 text-rose-300 border-rose-600/40',
  BLOCKED: 'bg-sky-500/15 text-sky-300 border-sky-600/40',
  ERROR: 'bg-slate-500/15 text-slate-300 border-slate-600/40',
  WARN: 'bg-amber-500/15 text-amber-300 border-amber-600/40',
}
export function Badge({ verdict, children }) {
  return (
    <span className={cls('inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-bold tracking-wide',
      VERDICT[verdict] || VERDICT.ERROR)}>
      {children || verdict}
    </span>
  )
}

export function Button({ children, onClick, disabled, variant = 'primary' }) {
  const v = {
    primary: 'bg-gradient-to-b from-indigo-500 to-indigo-600 text-white shadow-button hover:brightness-110',
    ghost: 'border border-line bg-panel text-slate-300 hover:border-slate-600 hover:text-slate-100',
    danger: 'border border-rose-500/30 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20',
  }[variant]
  return (
    <button onClick={onClick} disabled={disabled}
      className={cls('rounded-lg px-3.5 py-2 text-sm font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed', v)}>
      {children}
    </button>
  )
}

export function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1.5 text-[11.5px] font-semibold text-slate-400">
      <span>{label}</span>
      {children}
    </label>
  )
}

export function Input(props) {
  return <input {...props}
    className="rounded-lg border border-line bg-ink-900 px-2.5 py-1.5 text-sm font-normal text-slate-100 outline-none transition focus:border-indigo-500 focus:shadow-glow" />
}

export function Select({ children, ...props }) {
  return (
    <div className="relative">
      <select {...props}
        className="w-full appearance-none rounded-lg border border-line bg-ink-900 px-2.5 py-1.5 pr-7 text-sm font-normal text-slate-100 outline-none transition focus:border-indigo-500 focus:shadow-glow">
        {children}
      </select>
      <svg viewBox="0 0 24 24" className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
        fill="none" stroke="currentColor" strokeWidth="2">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  )
}

export function Textarea({ className, ...props }) {
  return <textarea {...props}
    className={cls(
      'w-full rounded-lg border border-line bg-ink-900 px-2.5 py-2 font-mono text-xs text-slate-100 outline-none transition focus:border-indigo-500 focus:shadow-glow disabled:opacity-50',
      className,
    )} />
}

export function Checkbox({ checked, onChange, label, disabled }) {
  return (
    <label className={cls('flex items-center gap-2 text-xs text-slate-300', disabled ? 'opacity-50' : 'cursor-pointer')}>
      <input type="checkbox" checked={!!checked} onChange={onChange} disabled={disabled}
        className="h-4 w-4 rounded border-slate-600 bg-ink-900 accent-indigo-500" />
      {label}
    </label>
  )
}
