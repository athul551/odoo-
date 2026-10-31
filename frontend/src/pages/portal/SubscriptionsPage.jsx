import { useCallback, useEffect, useState } from 'react'
import { DarkTable, Empty, Panel, StagePill, Td, Th } from '../../components/portal/ui'
import api, { apiError } from '../../lib/api'
import { dateOnly, money } from '../../lib/format'

export default function PortalSubscriptionsPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/subscriptions/', { params: { page_size: 200 } })
      setRows(data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-light tracking-tight text-paper">Subscriptions</h1>
        <p className="mt-2 text-sm text-muted">
          The contracts billed to your organization. Stage moves are made by Brightloop staff.
        </p>
      </header>

      {error && (
        <div className="rounded-panel border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      <Panel>
        {loading ? (
          <p className="text-sm text-faint">Loading subscriptions…</p>
        ) : (
          <DarkTable
            head={
              <>
                <Th>Number</Th>
                <Th>Plan</Th>
                <Th>Frequency</Th>
                <Th>Stage</Th>
                <Th>Term</Th>
                <Th className="text-right">Total</Th>
                <Th className="text-right">Invoices</Th>
              </>
            }
          >
            {rows.length === 0 && (
              <Empty
                colSpan={7}
                title="No subscriptions yet"
                hint="Your account manager will activate the first one."
              />
            )}
            {rows.map((subscription) => (
              <tr key={subscription.id}>
                <Td className="font-mono text-xs text-paper">{subscription.number}</Td>
                <Td>{subscription.plan_name}</Td>
                <Td className="capitalize">{subscription.billing_frequency}</Td>
                <Td>
                  <StagePill stage={subscription.stage} label={subscription.stage_display} />
                  {subscription.is_paused && (
                    <span className="ml-2 text-xs text-warn">paused</span>
                  )}
                </Td>
                <Td className="whitespace-nowrap">
                  {dateOnly(subscription.start_date)} → {dateOnly(subscription.expiry_date)}
                </Td>
                <Td className="text-right text-paper">{money(subscription.total)}</Td>
                <Td className="text-right">{subscription.invoice_count ?? 0}</Td>
              </tr>
            ))}
          </DarkTable>
        )}
      </Panel>
    </div>
  )
}
