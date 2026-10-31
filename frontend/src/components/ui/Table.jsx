export function Table({ children, className = '' }) {
  return (
    <div className={`-mx-6 overflow-x-auto ${className}`}>
      <table className="min-w-full divide-y divide-ink-600 text-left text-sm">{children}</table>
    </div>
  )
}

export function Th({ children, className = '' }) {
  return (
    <th
      className={`whitespace-nowrap bg-ink-900 px-6 py-3 text-[11px] font-medium uppercase tracking-[0.12em] text-faint ${className}`}
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

export function Tr({ children, className = '', onClick }) {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-ink-700 last:border-0 ${onClick ? 'cursor-pointer hover:bg-ink-700' : ''} ${className}`}
    >
      {children}
    </tr>
  )
}

export function EmptyRow({ colSpan, children = 'Nothing here yet.' }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-6 py-10 text-center text-sm text-faint">
        {children}
      </td>
    </tr>
  )
}
