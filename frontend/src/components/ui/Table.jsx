export function Table({ children, className = '' }) {
  return (
    <div className={`-mx-5 overflow-x-auto ${className}`}>
      <table className="min-w-full divide-y divide-slate-100 text-left text-sm">{children}</table>
    </div>
  )
}

export function Th({ children, className = '' }) {
  return (
    <th
      className={`whitespace-nowrap px-5 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500 ${className}`}
    >
      {children}
    </th>
  )
}

export function Td({ children, className = '', colSpan }) {
  return (
    <td colSpan={colSpan} className={`px-5 py-3 align-top text-slate-700 ${className}`}>
      {children}
    </td>
  )
}

export function Tr({ children, className = '', onClick }) {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-slate-50 last:border-0 ${onClick ? 'cursor-pointer hover:bg-slate-50' : ''} ${className}`}
    >
      {children}
    </tr>
  )
}

export function EmptyRow({ colSpan, children = 'Nothing here yet.' }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-5 py-8 text-center text-sm text-slate-400">
        {children}
      </td>
    </tr>
  )
}
