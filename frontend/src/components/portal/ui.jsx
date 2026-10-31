const PILL_TONES = {
  ok: 'border-ok/40 bg-ok/10 text-ok',
  warn: 'border-warn/40 bg-warn/10 text-warn',
  bad: 'border-bad/40 bg-bad/10 text-bad',
  info: 'border-info/40 bg-info/10 text-info',
  muted: 'border-ink-600 bg-ink-900 text-muted',
  accent: 'border-accent/40 bg-accent-soft text-accent',
}

export function Panel({ title, subtitle, actions, children, className = '' }) {
  return (
    <section className={`dark-panel ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-600 px-6 py-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-paper">{title}</h2>}
            {subtitle && <p className="mt-1 text-xs text-faint">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="px-6 py-5">{children}</div>
    </section>
  )
}

export function Kpi({ label, value, hint }) {
  return (
    <div className="dark-panel px-6 py-5">
      <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-faint">{label}</p>
      <p className="mt-2 text-3xl font-light tracking-tight text-paper">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export function Pill({ tone = 'muted', children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${PILL_TONES[tone] ?? PILL_TONES.muted}`}
    >
      {children}
    </span>
  )
}

const STAGE_TONES = {
  draft: 'muted',
  quotation: 'info',
  confirmed: 'warn',
  active: 'ok',
  closed: 'muted',
}

export function StagePill({ stage, label }) {
  return <Pill tone={STAGE_TONES[stage] ?? 'muted'}>{label ?? stage}</Pill>
}

const STATUS_TONES = {
  draft: 'muted',
  confirmed: 'info',
  paid: 'ok',
  cancelled: 'bad',
}

export function StatusPill({ status, label }) {
  return <Pill tone={STATUS_TONES[status] ?? 'muted'}>{label ?? status}</Pill>
}

export function DarkTable({ head, children }) {
  return (
    <div className="-mx-6 overflow-x-auto">
      <table className="min-w-full divide-y divide-ink-600 text-left text-sm">
        <thead className="bg-ink-900">
          <tr>{head}</tr>
        </thead>
        <tbody className="divide-y divide-ink-700">{children}</tbody>
      </table>
    </div>
  )
}

export function Th({ children, className = '' }) {
  return (
    <th
      className={`whitespace-nowrap px-6 py-3 text-[11px] font-medium uppercase tracking-[0.12em] text-faint ${className}`}
    >
      {children}
    </th>
  )
}

export function Td({ children, className = '', colSpan }) {
  return (
    <td colSpan={colSpan} className={`px-6 py-4 align-middle text-muted ${className}`}>
      {children}
    </td>
  )
}

export function Empty({ title, hint, colSpan }) {
  if (colSpan) {
    return (
      <tr>
        <td colSpan={colSpan} className="px-6 py-10 text-center">
          <p className="text-sm font-medium text-muted">{title}</p>
          {hint && <p className="mt-1 text-xs text-faint">{hint}</p>}
        </td>
      </tr>
    )
  }
  return (
    <div className="rounded-panel border border-dashed border-ink-600 px-6 py-10 text-center">
      <p className="text-sm font-medium text-muted">{title}</p>
      {hint && <p className="mt-1 text-xs text-faint">{hint}</p>}
    </div>
  )
}
