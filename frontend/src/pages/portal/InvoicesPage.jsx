import { useCallback, useEffect, useState } from 'react'
import { DarkTable, Empty, Panel, StatusPill, Td, Th } from '../../components/portal/ui'
import api, { apiError } from '../../lib/api'
import { dateOnly, money } from '../../lib/format'

const STATUSES = ['', 'draft', 'confirmed', 'paid', 'cancelled']

export default function PortalInvoicesPage() {
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/invoices/', {
        params: { page_size: 200, status: status || undefined },
      })
      setRows(data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-paper">Invoices</h1>
          <p className="mt-2 text-sm text-muted">
            Every period billed to your organization, with what is still due.
          </p>
        </div>
        <label className="block">
          <span className="mb-1.5 block text-[11px] uppercase tracking-[0.12em] text-faint">
            Status
          </span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="h-11 rounded-panel border border-ink-600 bg-ink-900 px-3 text-sm text-paper dark-focus"
          >
            {STATUSES.map((value) => (
              <option key={value || 'all'} value={value}>
                {value ? value[0].toUpperCase() + value.slice(1) : 'All statuses'}
              </option>
            ))}
          </select>
        </label>
      </header>

      {error && (
        <div className="rounded-panel border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      <Panel>
        {loading ? (
          <p className="text-sm text-faint">Loading invoices…</p>
        ) : (
          <DarkTable
            head={
              <>
                <Th>Invoice</Th>
                <Th>Period</Th>
                <Th>Due date</Th>
                <Th>Status</Th>
                <Th className="text-right">Total</Th>
                <Th className="text-right">Paid</Th>
                <Th className="text-right">Due</Th>
              </>
            }
          >
            {rows.length === 0 && (
              <Empty
                colSpan={7}
                title="No invoices match"
                hint={status ? 'Try another status.' : 'Billing has not run yet.'}
              />
            )}
            {rows.map((invoice) => (
              <tr key={invoice.id}>
                <Td className="font-mono text-xs text-paper">{invoice.number}</Td>
                <Td className="whitespace-nowrap">
                  {dateOnly(invoice.period_start)} → {dateOnly(invoice.period_end)}
                </Td>
                <Td className="whitespace-nowrap">{dateOnly(invoice.due_date)}</Td>
                <Td>
                  <StatusPill status={invoice.status} />
                </Td>
                <Td className="text-right text-paper">{money(invoice.total)}</Td>
                <Td className="text-right">{money(invoice.amount_paid)}</Td>
                <Td className="text-right">{money(invoice.amount_due)}</Td>
              </tr>
            ))}
          </DarkTable>
        )}
      </Panel>
    </div>
  )
}
