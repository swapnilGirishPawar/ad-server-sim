import React from 'react'

export const cls = (...a) => a.filter(Boolean).join(' ')

export function Card({ title, right, children, className }) {
  return (
    <div className={cls('rounded-xl border border-slate-800 bg-slate-900/60 p-4', className)}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
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
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={cls('mt-1 text-2xl font-bold tabular-nums', toneCls)}>{value}</div>
      {sub != null && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
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
    <span className={cls('inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold',
      VERDICT[verdict] || VERDICT.ERROR)}>
      {children || verdict}
    </span>
  )
}

export function Button({ children, onClick, disabled, variant = 'primary' }) {
  const v = {
    primary: 'bg-indigo-600 hover:bg-indigo-500 text-white',
    ghost: 'bg-slate-800 hover:bg-slate-700 text-slate-200',
    danger: 'bg-rose-600 hover:bg-rose-500 text-white',
  }[variant]
  return (
    <button onClick={onClick} disabled={disabled}
      className={cls('rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:opacity-40 disabled:cursor-not-allowed', v)}>
      {children}
    </button>
  )
}

export function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-400">
      <span>{label}</span>
      {children}
    </label>
  )
}

export function Input(props) {
  return <input {...props}
    className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-100 outline-none focus:border-indigo-500" />
}

export function Select({ children, ...props }) {
  return <select {...props}
    className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-100 outline-none focus:border-indigo-500">
    {children}
  </select>
}
