export const inputClass =
  'w-full rounded-panel border border-ink-600 bg-ink-900 px-3 py-2.5 text-sm text-paper placeholder:text-faint shadow-none focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:opacity-40'

export function Field({ label, hint, error, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      {label && (
        <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-faint">
          {label}
        </span>
      )}
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-faint">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-bad">{error}</span>}
    </label>
  )
}

export function TextInput({ className = '', ...props }) {
  return <input className={`${inputClass} ${className}`} {...props} />
}

export function Select({ className = '', children, ...props }) {
  return (
    <select className={`${inputClass} ${className}`} {...props}>
      {children}
    </select>
  )
}

export function Textarea({ className = '', rows = 3, ...props }) {
  return <textarea rows={rows} className={`${inputClass} ${className}`} {...props} />
}

export function Checkbox({ label, className = '', ...props }) {
  return (
    <label className={`flex items-center gap-2 text-sm text-muted ${className}`}>
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-ink-600 bg-ink-900 text-accent focus:ring-accent/40"
        {...props}
      />
      {label}
    </label>
  )
}

export function FormGrid({ children, columns = 2 }) {
  return (
    <div className={`grid gap-4 ${columns === 2 ? 'sm:grid-cols-2' : ''}`}>{children}</div>
  )
}
