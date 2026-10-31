export function money(value) {
  const number = Number(value ?? 0)
  if (Number.isNaN(number)) return String(value ?? '—')
  return number.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function dateOnly(value) {
  if (!value) return '—'
  return String(value).slice(0, 10)
}

export function dateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

export function bytes(value) {
  const size = Number(value ?? 0)
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} kB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function ms(value) {
  const number = Number(value ?? 0)
  return number < 1 ? '<1 ms' : `${number.toFixed(number < 10 ? 1 : 0)} ms`
}

export function todayISO() {
  const now = new Date()
  const offset = now.getTimezoneOffset()
  return new Date(now.getTime() - offset * 60000).toISOString().slice(0, 10)
}

export function titleize(value) {
  if (!value) return '—'
  return String(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}
