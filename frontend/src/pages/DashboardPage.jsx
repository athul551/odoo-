import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { money, titleize } from '../lib/format'

function Kpi({ label, value, hint }) {
  return (
    <div className="rounded-panel border border-ink-600 bg-ink-800 px-6 py-5">
      <p className="text-xs font-medium uppercase tracking-widest text-faint">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-paper">{value}</p>
      {hint && <p className="mt-1.5 text-xs text-faint">{hint}</p>}
    </div>
  )
}

export default function DashboardPage() {
  const { isAdmin, isStaff } = useAuth()
  const [summary, setSummary] = useState(null)
  const [chase, setChase] = useState(null)
  const [expiring, setExpiring] = useState(null)
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [ops, setOps] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/reporting/summary/')
      setSummary(data)
      if (isStaff) {
        api
          .get('/reporting/chase/', { params: { kind: 'overdue', page_size: 5 } })
          .then(({ data: chaseData }) => setChase(chaseData))
          .catch(() => setChase(null))
        api
          .get('/reporting/expiring/', { params: { within_days: 30, page_size: 5 } })
          .then(({ data: renewalData }) => setExpiring(renewalData))
          .catch(() => setExpiring(null))
      }
      if (isAdmin) {
        try {
          const overview = await api.get('/ops/overview/')
          setOps(overview.data)
        } catch {
          setOps(null)
        }
      }
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [isAdmin, isStaff])

  useEffect(() => {
    load()
  }, [load])

  const runPreview = async () => {
    setPreviewing(true)
    setError('')
    try {
      const { data } = await api.post('/billing-runs/run/', { dry_run: true })
      setPreview(data)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setPreviewing(false)
    }
  }

  const seed = async () => {
    setSeeding(true)
    setError('')
    setNotice('')
    try {
      const { data } = await api.post('/ops/demo-data/')
      setNotice(
        data.already_present
          ? 'Demo tenant already present — nothing new created.'
          : `Demo tenant created: ${data.subscriptions.length} subscriptions on ${data.plan}.`,
      )
      await load()
    } catch (err) {
      setError(apiError(err))
    } finally {
      setSeeding(false)
    }
  }

  if (loading && !summary) return <Loading label="Loading dashboard…" />

  return (
    <div className="space-y-16">
      {/* overview title */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-5xl font-light tracking-tight text-paper">Operations</h1>
          <p className="mt-2 text-sm text-faint">
            {summary && (
              <>
                Month-end view {summary.window.start} → {summary.window.end} · as of{' '}
                {summary.window.as_of}
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={load} disabled={loading}>
            Refresh
          </Button>
          {isAdmin && (
            <Button onClick={seed} disabled={seeding}>
              {seeding ? 'Seeding…' : 'Seed demo tenant'}
            </Button>
          )}
        </div>
      </header>

      <ErrorBox message={error} onRetry={load} />
      {notice && <div className="rounded-lg border border-ok/25 bg-ok/10 px-4 py-3 text-sm text-ok">{notice}</div>}

      {summary && (
        <>
          {/* KPI band */}
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="MRR" value={money(summary.mrr)} hint={`ARR ${money(summary.arr)}`} />
            <Kpi
              label="Active subscriptions"
              value={summary.active_subscriptions}
              hint={`${summary.paused_subscriptions} paused · ${titleize(
                summary.active_by_frequency ? Object.keys(summary.active_by_frequency)[0] ?? '' : '',
              )}`}
            />
            <Kpi
              label="Invoiced"
              value={money(summary.invoiced_total)}
              hint={`${summary.window.start} → ${summary.window.end}`}
            />
            <Kpi
              label="Collected"
              value={money(summary.collected_total)}
              hint={
                summary.overdue.count
                  ? `${summary.overdue.count} overdue · ${money(summary.overdue.amount)}`
                  : 'Nothing overdue'
              }
            />
          </div>

          {/* 8/4 split: revenue mix + overdue chase */}
          <div className="grid gap-8 xl:grid-cols-3">
            <Card className="xl:col-span-2" title="Revenue mix" subtitle="Active subscriptions normalised to a month">
              {Object.keys(summary.active_by_frequency).length === 0 ? (
                <p className="text-sm text-faint">No active subscriptions yet.</p>
              ) : (
                <div className="space-y-4">
                  {Object.entries(summary.active_by_frequency).map(([frequency, count]) => {
                    const total = summary.active_subscriptions || 1
                    const width = Math.round((count / total) * 100)
                    return (
                      <div key={frequency}>
                        <div className="flex items-center justify-between text-xs text-faint">
                          <span className="capitalize">{titleize(frequency)}</span>
                          <span>{count}</span>
                        </div>
                        <div className="mt-1.5 h-2 rounded-full bg-ink-700">
                          <div
                            className="h-2 rounded-full bg-accent"
                            style={{ width: `${width}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {summary && (
                <dl className="mt-8 grid grid-cols-2 gap-4 border-t border-ink-600 pt-6 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-xs text-faint">Outstanding</dt>
                    <dd className="mt-1 font-medium text-paper">{money(summary.outstanding.amount)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-faint">Overdue</dt>
                    <dd className="mt-1 font-medium text-bad">{money(summary.overdue.amount)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-faint">Invoiced</dt>
                    <dd className="mt-1 font-medium text-paper">{money(summary.invoiced_total)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-faint">Collected</dt>
                    <dd className="mt-1 font-medium text-ok">{money(summary.collected_total)}</dd>
                  </div>
                </dl>
              )}
            </Card>

            {isStaff && (
              <Card
                title="Overdue chase"
                subtitle="Past due date, oldest first"
                actions={
                  <Link to="/billing" className="text-xs font-medium text-accent hover:text-accent-hover">
                    Billing →
                  </Link>
                }
                bodyClassName=""
              >
                {chase && chase.results?.length > 0 ? (
                  <Table>
                    <thead>
                      <tr>
                        <Th>Invoice</Th>
                        <Th>Due</Th>
                        <Th className="text-right">Due now</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {chase.results.slice(0, 5).map((invoice) => (
                        <Tr key={invoice.number}>
                          <Td>
                            <p className="font-mono text-xs text-paper">{invoice.number}</p>
                            <p className="mt-0.5 text-xs text-faint">{invoice.customer}</p>
                          </Td>
                          <Td>
                            <span className="text-xs text-bad">{invoice.due_date}</span>
                          </Td>
                          <Td className="text-right text-paper">{invoice.amount_due}</Td>
                        </Tr>
                      ))}
                    </tbody>
                  </Table>
                ) : (
                  <p className="text-sm text-faint">
                    Nothing overdue — the collections list is empty.
                  </p>
                )}
                {chase && chase.count > chase.results?.length && (
                  <p className="mt-3 text-xs text-faint">
                    and {chase.count - chase.results.length} more ·{' '}
                    <Link to="/billing" className="text-accent hover:text-accent-hover">
                      all in Billing
                    </Link>
                  </p>
                )}
              </Card>
            )}

            {isStaff && (
              <Card
                title="Renewals due"
                subtitle="Terms ending in the next 30 days"
                actions={
                  <Link to="/subscriptions" className="text-xs font-medium text-accent hover:text-accent-hover">
                    Subscriptions →
                  </Link>
                }
                bodyClassName=""
              >
                {expiring && expiring.results?.length > 0 ? (
                  <Table>
                    <thead>
                      <tr>
                        <Th>Subscription</Th>
                        <Th>Expires</Th>
                        <Th className="text-right">Value</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {expiring.results.map((sub) => (
                        <Tr key={sub.number}>
                          <Td>
                            <Link
                              to={`/subscriptions/${sub.id}`}
                              className="font-mono text-xs text-paper hover:text-accent"
                            >
                              {sub.number}
                            </Link>
                            <p className="mt-0.5 text-xs text-faint">{sub.customer}</p>
                          </Td>
                          <Td>
                            <span className="text-xs text-warn">{sub.expiry_date}</span>
                          </Td>
                          <Td className="text-right text-paper">{money(sub.total)}</Td>
                        </Tr>
                      ))}
                    </tbody>
                  </Table>
                ) : (
                  <p className="text-sm text-faint">
                    Nothing expires in the next 30 days.
                  </p>
                )}
                {expiring && expiring.total > (expiring.results?.length ?? 0) && (
                  <p className="mt-3 text-xs text-faint">
                    and {expiring.total - expiring.results.length} more ·{' '}
                    <Link to="/subscriptions" className="text-accent hover:text-accent-hover">
                      all subscriptions
                    </Link>
                  </p>
                )}
              </Card>
            )}
          </div>

          {/* billing-day console */}
          {isStaff && (
            <section className="rounded-panel border border-ink-600 bg-ink-800 p-8">
              <div className="flex flex-wrap items-center justify-between gap-6">
                <div>
                  <h2 className="text-2xl font-medium text-paper">Billing day</h2>
                  <p className="mt-1.5 text-sm text-faint">
                    Preview what tonight's run would invoice — nothing is written.
                  </p>
                </div>
                <Button onClick={runPreview} disabled={previewing} size="lg">
                  {previewing ? 'Previewing…' : 'Preview billing day'}
                </Button>
              </div>

              {preview && (
                <div className="mt-6 border-t border-ink-600 pt-6">
                  <div className="flex flex-wrap items-center gap-3">
                    <Badge tone="indigo">
                      {preview.invoices} invoice(s) for {preview.subscriptions} subscription(s)
                    </Badge>
                    <Badge tone={preview.missed_periods ? 'amber' : 'slate'}>
                      {preview.missed_periods} missed period(s) of ended terms
                    </Badge>
                    {preview.problems?.length > 0 && (
                      <Badge tone="rose">{preview.problems.length} problem record(s)</Badge>
                    )}
                    <span className="text-xs text-faint">on {preview.on}</span>
                  </div>

                  {preview.items?.length > 0 && (
                    <Table className="mt-4">
                      <thead>
                        <tr>
                          <Th>Subscription</Th>
                          <Th>Customer</Th>
                          <Th>Period</Th>
                          <Th className="text-right">Estimated subtotal</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.items.slice(0, 6).map((item) => (
                          <Tr key={`${item.subscription}-${item.period_start}`}>
                            <Td className="font-mono text-xs text-paper">{item.subscription}</Td>
                            <Td>{item.customer}</Td>
                            <Td className="text-xs">
                              {item.period_start} → {item.period_end}
                            </Td>
                            <Td className="text-right text-paper">{item.estimated_subtotal}</Td>
                          </Tr>
                        ))}
                      </tbody>
                    </Table>
                  )}

                  {preview.truncated && (
                    <p className="mt-3 text-xs text-faint">
                      List truncated — run the full console under Billing for everything.
                    </p>
                  )}
                  <p className="mt-4 text-xs text-faint">
                    To execute for real,{' '}
                    <Link to="/billing" className="text-accent hover:text-accent-hover">
                      open the Billing console
                    </Link>
                    .
                  </p>
                </div>
              )}
            </section>
          )}

          {/* ops snapshot (admin) */}
          {ops && (
            <Card
              title="System"
              subtitle={ops.database?.version ? `PostgreSQL ${ops.database.version}` : 'Admin view'}
              actions={
                isAdmin && (
                  <Link to="/database" className="text-xs font-medium text-accent hover:text-accent-hover">
                    Open console →
                  </Link>
                )
              }
            >
              <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-xs text-faint">Migrations applied</dt>
                  <dd className="mt-1 font-medium text-paper">{ops.migrations.applied}</dd>
                </div>
                <div>
                  <dt className="text-xs text-faint">Pending</dt>
                  <dd className="mt-1">
                    <Badge tone={ops.migrations.pending ? 'amber' : 'ok'}>{ops.migrations.pending}</Badge>
                  </dd>
                </div>
                {ops.counts?.subscriptions != null && (
                  <div>
                    <dt className="text-xs text-faint">Subscriptions</dt>
                    <dd className="mt-1 font-medium text-paper">{ops.counts.subscriptions}</dd>
                  </div>
                )}
                {ops.counts?.invoices != null && (
                  <div>
                    <dt className="text-xs text-faint">Invoices</dt>
                    <dd className="mt-1 font-medium text-paper">{ops.counts.invoices}</dd>
                  </div>
                )}
              </dl>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
