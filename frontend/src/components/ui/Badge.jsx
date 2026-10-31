const TONES = {
  slate: 'bg-raised text-secondary',
  indigo: 'bg-accent/15 text-accent',
  emerald: 'bg-ok/15 text-ok',
  amber: 'bg-warn/15 text-warn',
  rose: 'bg-bad/15 text-bad',
  sky: 'bg-info/15 text-info',
}

export default function Badge({ tone = 'slate', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone] ?? TONES.slate} ${className}`}
    >
      {children}
    </span>
  )
}

const STAGE_TONES = {
  draft: 'slate',
  quotation: 'sky',
  confirmed: 'amber',
  active: 'emerald',
  closed: 'slate',
}

export function StageBadge({ stage, label }) {
  return <Badge tone={STAGE_TONES[stage] ?? 'slate'}>{label ?? stage}</Badge>
}

const STATUS_TONES = {
  draft: 'slate',
  confirmed: 'sky',
  paid: 'emerald',
  cancelled: 'rose',
}

export function StatusBadge({ status, label }) {
  return <Badge tone={STATUS_TONES[status] ?? 'slate'}>{label ?? status}</Badge>
}
