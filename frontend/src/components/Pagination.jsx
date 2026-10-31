import Button from './ui/Button'

export default function Pagination({ page, pageSize, count, onPage, busy = false }) {
  if (!count) return null
  const pages = Math.max(1, Math.ceil(count / pageSize))
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, count)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 text-xs text-faint">
      <span>
        {from}–{to} of {count}
      </span>
      <div className="flex items-center gap-2">
        <Button
          size="xs"
          variant="secondary"
          disabled={page <= 1 || busy}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </Button>
        <span>
          Page {page} / {pages}
        </span>
        <Button
          size="xs"
          variant="secondary"
          disabled={page >= pages || busy}
          onClick={() => onPage(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
