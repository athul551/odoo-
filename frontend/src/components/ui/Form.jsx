export const inputClass =
  'w-full rounded-lg border border-line bg-sunken px-4 h-[60px] text-[15px] text-primary placeholder:text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-60'

export const compactInputClass =
  'w-full rounded-lg border border-line bg-sunken px-3 py-2 text-sm text-primary placeholder:text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-60'

export function Field({ label, hint, error, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      {label && <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-muted">{label}</span>}
      {children}
      {hint && !error && <span className="mt-1.5 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1.5 block text-xs text-bad">{error}</span>}
    </label>
  )
}

export function TextInput({ className = '', compact = false, ...props }) {
  return <input className={`${compact ? compactInputClass : inputClass} ${className}`} {...props} />
}

export function Select({ className = '', compact = false, children, ...props }) {
  return (
    <select className={`${compact ? compactInputClass : inputClass} ${className}`} {...props}>
      {children}
    </select>
  )
}

export function Textarea({ className = '', rows = 3, ...props }) {
  return (
    <textarea
      rows={rows}
      className={`w-full rounded-lg border border-line bg-sunken px-3 py-2 text-sm text-primary placeholder:text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 ${className}`}
      {...props}
    />
  )
}

export function Checkbox({ label, className = '', ...props }) {
  return (
    <label className={`flex items-center gap-2 text-sm text-secondary ${className}`}>
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-line bg-sunken text-accent focus:ring-accent/40"
        {...props}
      />
      {label}
    </label>
  )
}

export function FormGrid({ children, columns = 2 }) {
  return (
    <div className={`grid gap-5 ${columns === 2 ? 'sm:grid-cols-2' : ''}`}>{children}</div>
  )
}
