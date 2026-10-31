import Button from './Button'

export function Spinner({ className = '' }) {
  return (
    <svg
      className={`h-4 w-4 animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
      <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center gap-2 px-1 py-6 text-sm text-slate-500">
      <Spinner />
      {label}
    </div>
  )
}

export function ErrorBox({ message, onRetry }) {
  if (!message) return null
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      <span className="whitespace-pre-wrap">{message}</span>
      {onRetry && (
        <Button size="xs" variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

export function SuccessBox({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
      <span className="whitespace-pre-wrap">{message}</span>
      {onDismiss && (
        <button type="button" className="text-emerald-600" onClick={onDismiss} aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title = 'Nothing here yet', hint, action }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}
