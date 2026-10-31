import { useCallback, useEffect, useState } from 'react'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Checkbox } from '../components/ui/Form'
import { ConfirmModal } from '../components/ui/Modal'
import Tabs from '../components/ui/Tabs'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { bytes, dateTime, ms, titleize } from '../lib/format'

export default function DatabasePage() {
  const [tab, setTab] = useState('overview')
  const [overview, setOverview] = useState(null)
  const [migrations, setMigrations] = useState(null)
  const [tables, setTables] = useState(null)
  const [logs, setLogs] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [applyOpen, setApplyOpen] = useState(false)
  const [applying, setApplying] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/ops/overview/')
      setOverview(data)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadMigrations = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/ops/migrations/')
      setMigrations(data)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTables = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/ops/tables/')
      setTables(data.tables ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadLogs = useCallback(async () => {
    try {
      const { data } = await api.get('/ops/logs/', { params: { limit: 100 } })
      setLogs(data)
    } catch (err) {
      setError(apiError(err))
    }
  }, [])

  useEffect(() => {
    if (tab === 'overview') loadOverview()
    if (tab === 'migrations') loadMigrations()
    if (tab === 'tables') loadTables()
    if (tab === 'requests' || tab === 'sql') loadLogs()
  }, [tab, loadOverview, loadMigrations, loadTables, loadLogs])

  useEffect(() => {
    if (!autoRefresh || (tab !== 'requests' && tab !== 'sql')) return undefined
    const timer = setInterval(loadLogs, 4000)
    return () => clearInterval(timer)
  }, [autoRefresh, tab, loadLogs])

  const applyMigrations = async () => {
    setApplying(true)
    setError('')
    setNotice('')
    try {
      const { data } = await api.post('/ops/migrations/')
      setNotice(data.output || 'Migrations applied.')
      setApplyOpen(false)
      await loadMigrations()
      await loadOverview()
    } catch (err) {
      setError(apiError(err))
      setApplyOpen(false)
    } finally {
      setApplying(false)
    }
  }

  const clearLogs = async () => {
    try {
      await api.delete('/ops/logs/')
      await loadLogs()
    } catch (err) {
      setError(apiError(err))
    }
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-primary">Database</h1>
          <p className="mt-1 text-sm text-secondary">
            Migrations, table contents and the SQL the console just ran.
          </p>
        </div>
        {overview && (
          <Badge tone={overview.ops_enabled ? 'emerald' : 'rose'}>
            {overview.ops_enabled ? 'Ops tools enabled' : 'Ops tools disabled'}
          </Badge>
        )}
      </header>

      <ErrorBox message={error} />

      {notice && (
        <div className="whitespace-pre-wrap rounded-lg border border-ok/25 bg-ok/10 px-4 py-3 font-mono text-xs text-ok">
          {notice}
        </div>
      )}

      <Tabs
        tabs={[
          { id: 'overview', label: 'Overview' },
          {
            id: 'migrations',
            label: 'Migrations',
            count: overview?.migrations?.pending || undefined,
          },
          { id: 'tables', label: 'Tables' },
          { id: 'requests', label: 'Requests' },
          { id: 'sql', label: 'SQL log' },
        ]}
        active={tab}
        onChange={(next) => {
          setNotice('')
          setTab(next)
        }}
      />

      {loading && !overview && tab === 'overview' && <Loading />}

      {tab === 'overview' && overview && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="Connection">
            <dl className="space-y-2 text-sm">
              {[
                ['Engine', overview.database.engine],
                ['Database', overview.database.name],
                ['Host', `${overview.database.host}:${overview.database.port}`],
                ['Version', overview.database.version],
                ['DEBUG', overview.debug ? 'on' : 'off'],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-4">
                  <dt className="text-secondary">{label}</dt>
                  <dd className="truncate text-right font-medium text-secondary">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="Migrations">
            <div className="flex items-center gap-2">
              <Badge tone="emerald">{overview.migrations.applied} applied</Badge>
              <Badge tone={overview.migrations.pending ? 'amber' : 'slate'}>
                {overview.migrations.pending} pending
              </Badge>
            </div>
            <p className="mt-3 text-xs text-secondary">
              The migration list lives in the Migrations tab; applying runs the same{' '}
              <code className="rounded bg-raised px-1">manage.py migrate</code> you would run in a
              terminal.
            </p>
          </Card>

          <Card title="Rows by entity" className="lg:col-span-2">
            <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
              {[
                ['Customers', overview.counts.customers],
                ['Products', overview.counts.products],
                ['Plans', overview.counts.plans],
                ['Subscriptions', overview.counts.subscriptions],
                ['Invoices', overview.counts.invoices],
                ['Payments', overview.counts.payments],
                ['Billing runs', overview.counts.billing_runs],
                ['Users', overview.counts.users],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-line px-3 py-2">
                  <p className="text-xs text-muted">{label}</p>
                  <p className="text-lg font-semibold text-primary">{value}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-1">
              {Object.entries(overview.counts.subscriptions_by_stage).map(([stage, value]) => (
                <Badge key={stage}>
                  {titleize(stage)}: {value}
                </Badge>
              ))}
            </div>
          </Card>
        </div>
      )}

      {tab === 'migrations' && migrations && (
        <Card
          title="Migration state"
          subtitle="Pending migrations are applied by the button; the output is shown above."
          actions={
            <Button size="sm" onClick={() => setApplyOpen(true)}>
              Apply pending migrations
            </Button>
          }
        >
          <Table>
            <thead>
              <tr>
                <Th>App</Th>
                <Th>Applied</Th>
                <Th>Pending</Th>
                <Th>Latest applied</Th>
              </tr>
            </thead>
            <tbody>
              {migrations.apps.map((row) => (
                <Tr key={row.app}>
                  <Td className="font-medium text-primary">{row.app}</Td>
                  <Td>
                    <Badge tone="emerald">{row.applied.length}</Badge>
                  </Td>
                  <Td>
                    {row.pending.length ? (
                      <div className="flex flex-wrap gap-1">
                        {row.pending.map((name) => (
                          <Badge key={name} tone="amber">
                            {name}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </Td>
                  <Td className="text-secondary">
                    {row.latest_applied_at ? dateTime(row.latest_applied_at) : '—'}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}

      {tab === 'tables' && tables && (
        <Card title="Tables" subtitle="Exact row counts and on-disk size, straight from Postgres.">
          <Table>
            <thead>
              <tr>
                <Th>Table</Th>
                <Th>Rows</Th>
                <Th>Size</Th>
              </tr>
            </thead>
            <tbody>
              {tables.length === 0 && <EmptyRow colSpan={3}>No tables.</EmptyRow>}
              {tables.map((row) => (
                <Tr key={row.table}>
                  <Td className="font-mono text-xs text-secondary">{row.table}</Td>
                  <Td>{row.rows}</Td>
                  <Td className="text-secondary">{bytes(row.bytes)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}

      {(tab === 'requests' || tab === 'sql') && (
        <Card
          title={tab === 'requests' ? 'Request log' : 'SQL log'}
          subtitle={`The last ${logs?.max_entries ?? 300} events in this worker process.`}
          actions={
            <div className="flex items-center gap-3">
              <Checkbox
                label="Auto-refresh"
                checked={autoRefresh}
                onChange={(event) => setAutoRefresh(event.target.checked)}
              />
              <Button size="sm" variant="secondary" onClick={loadLogs}>
                Refresh
              </Button>
              <Button size="sm" variant="ghost" onClick={clearLogs}>
                Clear
              </Button>
            </div>
          }
        >
          {!logs ? (
            <Loading />
          ) : tab === 'requests' ? (
            <Table>
              <thead>
                <tr>
                  <Th>Method</Th>
                  <Th>Path</Th>
                  <Th>Status</Th>
                  <Th>Duration</Th>
                  <Th>SQL</Th>
                  <Th>User</Th>
                </tr>
              </thead>
              <tbody>
                {logs.requests.length === 0 && (
                  <EmptyRow colSpan={6}>No requests recorded yet.</EmptyRow>
                )}
                {logs.requests.map((row, index) => (
                  <Tr key={index}>
                    <Td className="font-mono text-xs">{row.method}</Td>
                    <Td className="font-mono text-xs">
                      {row.path}
                      {row.query ? `?${row.query}` : ''}
                    </Td>
                    <Td>
                      <Badge
                        tone={
                          row.status >= 500
                            ? 'rose'
                            : row.status >= 400
                              ? 'amber'
                              : 'emerald'
                        }
                      >
                        {row.status}
                      </Badge>
                    </Td>
                    <Td className="text-secondary">{ms(row.ms)}</Td>
                    <Td className="text-secondary">{row.sql_count}</Td>
                    <Td className="text-secondary">{row.user || 'anonymous'}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Path</Th>
                  <Th>Duration</Th>
                  <Th>SQL</Th>
                  <Th>Params</Th>
                </tr>
              </thead>
              <tbody>
                {logs.sql.length === 0 && <EmptyRow colSpan={4}>No SQL recorded yet.</EmptyRow>}
                {logs.sql.map((row, index) => (
                  <Tr key={index}>
                    <Td className="whitespace-nowrap font-mono text-xs text-secondary">
                      {row.method} {row.path}
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-secondary">{ms(row.ms)}</Td>
                    <Td className="max-w-xl break-words font-mono text-xs text-secondary">
                      {row.sql}
                    </Td>
                    <Td className="max-w-xs break-words font-mono text-xs text-muted">
                      {row.params}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      <ConfirmModal
        open={applyOpen}
        title="Apply pending migrations"
        message="This runs migrate against the configured database. Take a backup first if the data matters."
        confirmLabel="Run migrate"
        tone="primary"
        busy={applying}
        onConfirm={applyMigrations}
        onClose={() => setApplyOpen(false)}
      />
    </div>
  )
}
