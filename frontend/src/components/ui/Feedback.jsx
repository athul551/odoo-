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
    <div className="flex items-center gap-2 px-1 py-6 text-sm text-secondary">
      <Spinner />
      {label}
    </div>
  )
}

export function ErrorBox({ message, onRetry }) {
  if (!message) return null
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-bad/25 bg-bad/10 px-4 py-3 text-sm text-bad">
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
    <div className="flex items-start justify-between gap-3 rounded-lg border border-ok/25 bg-ok/10 px-4 py-3 text-sm text-ok">
      <span className="whitespace-pre-wrap">{message}</span>
      {onDismiss && (
        <button type="button" className="text-ok" onClick={onDismiss} aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title = 'Nothing here yet', hint, action }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-6 py-10 text-center">
      <p className="text-sm font-medium text-secondary">{title}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}
