const VARIANTS = {
  primary: 'bg-accent text-base hover:bg-accent-hover disabled:bg-accent/40',
  secondary:
    'border border-line bg-panel text-primary hover:bg-raised disabled:text-muted disabled:opacity-60',
  danger: 'bg-bad/90 text-base hover:bg-bad disabled:bg-bad/40',
  ghost: 'text-secondary hover:bg-raised hover:text-primary',
}

const SIZES = {
  xs: 'px-2 py-1 text-xs rounded-md',
  sm: 'px-2.5 py-1.5 text-xs rounded-md',
  md: 'px-4 py-2 text-sm rounded-lg',
  lg: 'h-[60px] px-6 text-[15px] rounded-lg',
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
      className={`inline-flex items-center justify-center gap-1.5 font-medium transition disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
