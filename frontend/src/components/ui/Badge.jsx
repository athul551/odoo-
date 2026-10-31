const TONES = {
  slate: 'border-ink-600 bg-ink-900 text-muted',
  muted: 'border-ink-600 bg-ink-900 text-muted',
  indigo: 'border-accent/40 bg-accent-soft text-accent',
  accent: 'border-accent/40 bg-accent-soft text-accent',
  emerald: 'border-ok/40 bg-ok/10 text-ok',
  ok: 'border-ok/40 bg-ok/10 text-ok',
  amber: 'border-warn/40 bg-warn/10 text-warn',
  warn: 'border-warn/40 bg-warn/10 text-warn',
  rose: 'border-bad/40 bg-bad/10 text-bad',
  bad: 'border-bad/40 bg-bad/10 text-bad',
  sky: 'border-info/40 bg-info/10 text-info',
  info: 'border-info/40 bg-info/10 text-info',
}

export default function Badge({ tone = 'slate', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone] ?? TONES.slate} ${className}`}
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

export function StageBadge({ stage, label }) {
  return <Badge tone={STAGE_TONES[stage] ?? 'muted'}>{label ?? stage}</Badge>
}

const STATUS_TONES = {
  draft: 'muted',
  confirmed: 'info',
  paid: 'ok',
  cancelled: 'bad',
}

export function StatusBadge({ status, label }) {
  return <Badge tone={STATUS_TONES[status] ?? 'muted'}>{label ?? status}</Badge>
}
