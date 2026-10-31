const TONES = {
  slate: 'bg-slate-100 text-slate-700',
  indigo: 'bg-indigo-50 text-indigo-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  amber: 'bg-amber-50 text-amber-800',
  rose: 'bg-rose-50 text-rose-700',
  sky: 'bg-sky-50 text-sky-700',
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
