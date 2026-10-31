import { useCallback, useEffect, useState } from 'react'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Field, TextInput } from '../components/ui/Form'
import Tabs from '../components/ui/Tabs'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { dateOnly, money, todayISO } from '../lib/format'

function Kpi({ label, value, hint }) {
  return (
    <div className="dark-panel px-6 py-5">
      <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-faint">{label}</p>
      <p className="mt-2 text-3xl font-light tracking-tight text-paper">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export default function ReportingPage() {
  const [asOf, setAsOf] = useState(todayISO())
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [kind, setKind] = useState('overdue')
  const [chase, setChase] = useState([])
  const [chaseLoading, setChaseLoading] = useState(false)

  const loadSummary = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/reporting/summary/', { params: { as_of: asOf } })
      setSummary(data)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [asOf])

  const loadChase = useCallback(async () => {
    setChaseLoading(true)
    setError('')
    try {
      const { data } = await api.get('/reporting/chase/', {
        params: { kind, as_of: asOf, page_size: 50 },
      })
      setChase(data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setChaseLoading(false)
    }
  }, [kind, asOf])

  useEffect(() => {
    loadSummary()
  }, [loadSummary])

  useEffect(() => {
    loadChase()
  }, [loadChase])

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-light tracking-tight text-paper">Reporting</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            The month-end picture and the two chase lists, computed in SQL from the same ledger the
            console writes to.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <Field label="As of">
            <TextInput
              type="date"
              value={asOf}
              onChange={(event) => setAsOf(event.target.value)}
              className="w-40"
            />
          </Field>
          <Button
            variant="secondary"
            onClick={() => {
              loadSummary()
              loadChase()
            }}
            disabled={loading}
          >
            Refresh
          </Button>
        </div>
      </header>

      <ErrorBox message={error} onRetry={loadSummary} />

      {loading && !summary ? (
        <Loading label="Computing the month-end picture…" />
      ) : (
        summary && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Kpi label="MRR" value={money(summary.mrr)} hint={`ARR ${money(summary.arr)}`} />
              <Kpi
                label="Active subscriptions"
                value={summary.active_subscriptions}
                hint={`${summary.paused_subscriptions} paused`}
              />
              <Kpi
                label="Invoiced"
                value={money(summary.invoiced_total)}
                hint={`${summary.window.start} → ${summary.window.end}`}
              />
              <Kpi
                label="Collected"
                value={money(summary.collected_total)}
                hint="Payments in the window"
              />
              <Kpi
                label="Outstanding"
                value={money(summary.outstanding.amount)}
                hint={`${summary.outstanding.count} invoice(s) not yet due`}
              />
              <Kpi
                label="Overdue"
                value={money(summary.overdue.amount)}
                hint={`${summary.overdue.count} invoice(s) past due`}
              />
              <Kpi
                label="Window"
                value={`${dateOnly(summary.window.start)}`}
                hint={`to ${dateOnly(summary.window.end)}`}
              />
              <Kpi
                label="As of"
                value={dateOnly(summary.window.as_of)}
                hint="Counts and MRR snapshot"
              />
            </div>

            <Card
              title="Collections chase"
              subtitle="Confirmed invoices only, most overdue first."
              actions={
                <Tabs
                  tabs={[
                    { id: 'overdue', label: 'Overdue', count: summary.overdue.count },
                    {
                      id: 'outstanding',
                      label: 'Outstanding',
                      count: summary.outstanding.count,
                    },
                  ]}
                  active={kind}
                  onChange={setKind}
                />
              }
              bodyClassName="pb-2"
            >
              {chaseLoading ? (
                <Loading label="Loading the chase list…" />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Invoice</Th>
                      <Th>Customer</Th>
                      <Th>Subscription</Th>
                      <Th>Period</Th>
                      <Th>Due date</Th>
                      <Th className="text-right">Total</Th>
                      <Th className="text-right">Paid</Th>
                      <Th className="text-right">Due</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {chase.length === 0 && (
                      <EmptyRow colSpan={8}>
                        Nothing in this list — the ledger is clean.
                      </EmptyRow>
                    )}
                    {chase.map((row) => (
                      <Tr key={row.number}>
                        <Td className="font-mono text-xs text-paper">{row.number}</Td>
                        <Td>{row.customer}</Td>
                        <Td className="font-mono text-xs">{row.subscription}</Td>
                        <Td className="whitespace-nowrap">
                          {dateOnly(row.period[0])} → {dateOnly(row.period[1])}
                        </Td>
                        <Td className="whitespace-nowrap">{dateOnly(row.due_date)}</Td>
                        <Td className="text-right text-paper">{money(row.total)}</Td>
                        <Td className="text-right">{money(row.amount_paid)}</Td>
                        <Td className="text-right text-warn">{money(row.amount_due)}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>
          </>
        )
      )}
    </div>
  )
}
