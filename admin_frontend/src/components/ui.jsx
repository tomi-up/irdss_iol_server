import { useEffect } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { ALERT_TONES, BADGE_TONES, CARD, ICON_BADGE, STAT_TONES } from './styles'

export function Badge({ children, tone = 'slate' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
        BADGE_TONES[tone] || BADGE_TONES.slate
      }`}
    >
      {children}
    </span>
  )
}

export function StatCard({ label, value, hint, tone = 'slate', icon }) {
  return (
    <div className={`${CARD} p-5`}>
      {icon ? <div className={`${ICON_BADGE} mb-4 text-lg`}>{icon}</div> : null}
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-3xl font-bold ${STAT_TONES[tone] || STAT_TONES.slate}`}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function Alert({ tone = 'red', title, children, onDismiss }) {
  // Success alerts get a checkmark badge + bold heading (defaulting to "Success"
  // when the caller doesn't pass one) — every other tone keeps its prior compact form.
  const isSuccess = tone === 'green'
  const heading = title ?? (isSuccess ? 'Success' : undefined)

  return (
    <div
      className={`mb-4 flex items-start gap-3 text-sm ${
        isSuccess ? 'rounded-2xl px-5 py-4' : 'rounded-xl px-4 py-3'
      } border ${ALERT_TONES[tone] || ALERT_TONES.red}`}
    >
      {isSuccess ? <CheckCircle2 size={20} className="mt-0.5 shrink-0" strokeWidth={2} /> : null}
      <div className="flex-1">
        {heading ? <p className="font-semibold">{heading}</p> : null}
        <div className={heading ? 'mt-1' : ''}>{children}</div>
      </div>
      {onDismiss ? (
        <button type="button" onClick={onDismiss} className="shrink-0 font-bold opacity-60 hover:opacity-100">
          ×
        </button>
      ) : null}
    </div>
  )
}

export function Spinner({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-red-600" />
      {label}
    </div>
  )
}

export function EmptyState({ title, hint }) {
  return (
    <div className="py-12 text-center">
      <p className="text-sm font-semibold text-slate-600">{title}</p>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
    </div>
  )
}

// Accessible modal shell; closes on Escape and on backdrop click.
export function Modal({ open, title, onClose, children, footer, wide = false }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div
        className={`relative flex max-h-[88vh] w-full flex-col rounded-2xl border border-slate-200/80 bg-white shadow-xl ${
          wide ? 'max-w-3xl' : 'max-w-lg'
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-2xl leading-none text-slate-400 transition hover:text-slate-700"
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer ? (
          <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">{footer}</div>
        ) : null}
      </div>
    </div>
  )
}
