const VARIANTS = {
  primary:
    'bg-accent text-ink-950 hover:bg-accent-hover disabled:bg-accent/40 disabled:text-ink-950/60',
  secondary:
    'border border-ink-600 bg-transparent text-paper hover:border-ink-500 hover:bg-ink-700 disabled:text-faint',
  danger:
    'border border-bad/40 bg-bad/10 text-bad hover:bg-bad/20 disabled:opacity-40',
  success: 'bg-ok text-ink-950 hover:bg-ok/90 disabled:opacity-40',
  ghost: 'text-muted hover:bg-ink-700 hover:text-paper disabled:text-faint',
}

const SIZES = {
  xs: 'px-2 py-1 text-xs',
  sm: 'px-2.5 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
}

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  type = 'button',
  className = '',
  ...props
}) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition duration-150 ease-calm focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
