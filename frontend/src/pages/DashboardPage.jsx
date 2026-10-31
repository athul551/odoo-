import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateTime, money, titleize } from '../lib/format'

function Kpi({ label, value, hint, tone = 'text-slate-900' }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

export default function DashboardPage() {
  const { isAdmin } = useAuth()
  const [summary, setSummary] = useState(null)
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
  }, [isAdmin])

  useEffect(() => {
    load()
  }, [load])

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

  const counts = ops?.counts

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            The numbers the finance lead reads, computed from the same API the console calls.
          </p>
        </div>
        <div className="flex gap-2">
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
      {notice && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      )}

      {summary && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="MRR" value={money(summary.mrr)} hint={`ARR ${money(summary.arr)}`} />
            <Kpi
              label="Active subscriptions"
              value={summary.active_subscriptions}
              hint={`${summary.paused_subscriptions} paused`}
            />
            <Kpi
              label="Invoiced this window"
              value={money(summary.invoiced_total)}
              hint={`${summary.window.start} → ${summary.window.end}`}
            />
            <Kpi
              label="Collected"
              value={money(summary.collected_total)}
              hint={`Outstanding ${money(summary.outstanding.amount)} · Overdue ${money(summary.overdue.amount)}`}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Revenue mix" subtitle="Active subscriptions normalised to a month">
              {Object.keys(summary.active_by_frequency).length === 0 ? (
                <p className="text-sm text-slate-400">No active subscriptions yet.</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(summary.active_by_frequency).map(([frequency, count]) => {
                    const total = summary.active_subscriptions || 1
                    const width = Math.round((count / total) * 100)
                    return (
                      <div key={frequency}>
                        <div className="flex items-center justify-between text-xs text-slate-500">
                          <span className="capitalize">{titleize(frequency)}</span>
                          <span>{count}</span>
                        </div>
                        <div className="mt-1 h-2 rounded-full bg-slate-100">
                          <div
                            className="h-2 rounded-full bg-indigo-500"
                            style={{ width: `${width}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>

            <Card
              title="Database"
              subtitle={ops ? `${ops.database.version}` : 'Admin view'}
              actions={
                isAdmin && (
                  <Link
                    to="/database"
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                  >
                    Open console →
                  </Link>
                )
              }
            >
              {ops ? (
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-slate-400">Database</dt>
                    <dd className="truncate font-medium text-slate-700">{ops.database.name}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-400">Host</dt>
                    <dd className="truncate font-medium text-slate-700">{ops.database.host}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-400">Migrations applied</dt>
                    <dd className="font-medium text-slate-700">{ops.migrations.applied}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-400">Pending migrations</dt>
                    <dd>
                      <Badge tone={ops.migrations.pending ? 'amber' : 'emerald'}>
                        {ops.migrations.pending}
                      </Badge>
                    </dd>
                  </div>
                  {counts && (
                    <>
                      <div>
                        <dt className="text-xs text-slate-400">Subscriptions</dt>
                        <dd className="font-medium text-slate-700">{counts.subscriptions}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-slate-400">Invoices</dt>
                        <dd className="font-medium text-slate-700">{counts.invoices}</dd>
                      </div>
                    </>
                  )}
                </dl>
              ) : (
                <p className="text-sm text-slate-400">
                  {isAdmin
                    ? 'Ops tools are disabled (OPS_TOOLS_ENABLED).'
                    : 'Sign in as an admin to inspect migrations and SQL.'}
                </p>
              )}
            </Card>
          </div>

          {counts && (
            <Card title="What is in the database" subtitle="Live row counts from the ops endpoint">
              <Table>
                <thead>
                  <tr>
                    <Th>Entity</Th>
                    <Th>Total</Th>
                    <Th>Breakdown</Th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Customers', counts.customers, null],
                    ['Products', counts.products, null],
                    ['Plans', counts.plans, null],
                    ['Subscriptions', counts.subscriptions, counts.subscriptions_by_stage],
                    ['Invoices', counts.invoices, counts.invoices_by_status],
                    ['Payments', counts.payments, null],
                    ['Billing runs', counts.billing_runs, null],
                    ['Users', counts.users, null],
                  ].map(([label, total, breakdown]) => (
                    <Tr key={label}>
                      <Td className="font-medium text-slate-800">{label}</Td>
                      <Td>{total}</Td>
                      <Td>
                        {breakdown ? (
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(breakdown).map(([key, value]) => (
                              <Badge key={key}>
                                {titleize(key)}: {value}
                              </Badge>
                            ))}
                          </div>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
              {ops && (
                <p className="mt-3 text-xs text-slate-400">
                  Snapshot at {dateTime(new Date().toISOString())}
                </p>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  )
}
