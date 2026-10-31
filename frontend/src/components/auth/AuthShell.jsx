import { Link } from 'react-router-dom'

/**
 * Calm-dark auth shell: brand panel on the left (7/12), focused form on the
 * right (5/12), with a raised panel around the form. Shared by sign-in,
 * sign-up, forgot and reset so the surface never jumps.
 */
export default function AuthShell({ eyebrow, title, subtitle, children, footer }) {
  return (
    <div className="dark-page min-h-screen">
      <div className="mx-auto grid min-h-screen max-w-[1440px] lg:grid-cols-12">
        <aside className="dark-grid relative hidden flex-col justify-between border-r border-ink-600 px-20 py-24 lg:col-span-7 lg:flex">
          <Link to="/login" className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-bold text-ink-950">
              B
            </span>
            <span className="text-sm font-semibold tracking-wide text-paper">Brightloop</span>
          </Link>

          <div className="max-w-xl">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-faint">
              Subscription operations
            </p>
            <h2 className="mt-5 text-5xl font-light leading-[1.1] tracking-tight text-paper">
              Calm control over every contract, invoice and payment.
            </h2>
            <ul className="mt-10 space-y-4 text-base text-muted">
              {[
                'Plans, quotations and the full subscription lifecycle',
                'Idempotent billing runs with a preview before anything is issued',
                'A ledger that refuses overpayment and keeps every period accounted for',
              ].map((line) => (
                <li key={line} className="flex gap-4">
                  <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {line}
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs text-faint">
            Draft → Quotation → Confirmed → Active → Closed. Nothing skipped, nothing billed twice.
          </p>
        </aside>

        <main className="flex flex-col justify-center px-6 py-16 sm:px-12 lg:col-span-5 lg:px-20">
          <div className="mx-auto w-full max-w-md">
            <div className="mb-10 lg:hidden">
              <Link to="/login" className="flex items-center gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-bold text-ink-950">
                  B
                </span>
                <span className="text-sm font-semibold tracking-wide">Brightloop</span>
              </Link>
            </div>

            {eyebrow && (
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-faint">{eyebrow}</p>
            )}
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-paper">{title}</h1>
            {subtitle && <p className="mt-2 text-sm leading-relaxed text-muted">{subtitle}</p>}

            <div className="dark-panel mt-10 p-8 sm:p-10">{children}</div>
            {footer && <div className="mt-8 text-center text-sm text-muted">{footer}</div>}
          </div>
        </main>
      </div>
    </div>
  )
}

export function AuthField({ label, hint, error, action, children }) {
  return (
    <label className="block">
      <span className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-faint">
          {label}
        </span>
        {action}
      </span>
      {children}
      {hint && !error && <span className="mt-1.5 block text-xs text-faint">{hint}</span>}
      {error && <span className="mt-1.5 block text-xs text-bad">{error}</span>}
    </label>
  )
}

export function AuthInput({ className = '', ...props }) {
  return (
    <input
      className={`h-[60px] w-full rounded-panel border border-ink-600 bg-ink-900 px-4 text-sm text-paper placeholder:text-faint dark-focus disabled:opacity-40 ${className}`}
      {...props}
    />
  )
}

export function AuthButton({ children, className = '', ...props }) {
  return (
    <button
      className={`h-[60px] w-full rounded-panel bg-accent text-sm font-semibold text-ink-950 transition duration-150 ease-calm hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function AuthError({ message }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className="rounded-panel border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad"
    >
      {message}
    </div>
  )
}

export function AuthNotice({ message }) {
  if (!message) return null
  return (
    <div className="rounded-panel border border-ok/40 bg-ok/10 px-4 py-3 text-sm text-ok">
      {message}
    </div>
  )
}

export function AuthTextLink({ to, children, className = 'text-xs' }) {
  return (
    <Link
      to={to}
      className={`font-medium text-accent transition hover:text-accent-hover ${className}`}
    >
      {children}
    </Link>
  )
}
