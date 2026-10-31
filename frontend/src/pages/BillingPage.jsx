import { useCallback, useEffect, useState } from 'react'
import InvoiceBrowser from '../components/billing/InvoiceBrowser'
import PaymentsLedger from '../components/billing/PaymentsLedger'
import Pagination from '../components/Pagination'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { EmptyState, ErrorBox, Loading } from '../components/ui/Feedback'
import { Field, TextInput } from '../components/ui/Form'
import Modal, { ConfirmModal } from '../components/ui/Modal'
import Tabs from '../components/ui/Tabs'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { dateOnly, dateTime, money, todayISO } from '../lib/format'

function RunReport({ run }) {
  const report = run.report ?? {}
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge tone="emerald">Billed {run.billed_count}</Badge>
        <Badge tone="sky">Already billed {run.skipped_count}</Badge>
        <Badge tone={run.failed_count ? 'rose' : 'slate'}>Failed {run.failed_count}</Badge>
        {report.skipped_locked?.length > 0 && (
          <Badge tone="amber">Locked {report.skipped_locked.length}</Badge>
        )}
      </div>

      {report.failed?.length > 0 && (
        <div className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2">
          <p className="text-xs font-semibold text-bad">Records that could not be billed</p>
          <ul className="mt-1 space-y-1 text-xs text-bad">
            {report.failed.map((failure, index) => (
              <li key={index}>
                <span className="font-medium">{failure.subscription}</span>: {failure.error}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.billed?.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs font-medium text-muted">
            Billed periods ({report.billed.length})
          </summary>
          <ul className="mt-1 space-y-0.5 text-xs text-faint">
            {report.billed.map(([number, period], index) => (
              <li key={index}>
                {number} · {period}
              </li>
            ))}
          </ul>
        </details>
      )}

      {report.skipped_already_billed?.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs font-medium text-muted">
            Already billed ({report.skipped_already_billed.length})
          </summary>
          <ul className="mt-1 space-y-0.5 text-xs text-faint">
            {report.skipped_already_billed.map(([number, period], index) => (
              <li key={index}>
                {number} · {period}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export default function BillingPage() {
  const [tab, setTab] = useState('day')

  const [on, setOn] = useState(todayISO())
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const [runs, setRuns] = useState([])
  const [runCount, setRunCount] = useState(0)
  const [runPage, setRunPage] = useState(1)
  const [runsLoading, setRunsLoading] = useState(false)
  const [selectedRun, setSelectedRun] = useState(null)

  const loadRuns = useCallback(async () => {
    setRunsLoading(true)
    try {
      const { data } = await api.get('/billing-runs/', {
        params: { page: runPage, page_size: 15 },
      })
      setRuns(data.results ?? [])
      setRunCount(data.count ?? 0)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setRunsLoading(false)
    }
  }, [runPage])

  useEffect(() => {
    if (tab === 'runs') loadRuns()
  }, [tab, loadRuns])

  const runPreview = async () => {
    setRunning(true)
    setError('')
    setResult(null)
    try {
      const { data } = await api.post('/billing-runs/run/', { on, dry_run: true })
      setPreview(data)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setRunning(false)
    }
  }

  const runBilling = async () => {
    setRunning(true)
    setError('')
    try {
      const { data } = await api.post('/billing-runs/run/', { on, dry_run: false })
      setResult(data)
      setPreview(null)
      setConfirmOpen(false)
      await loadRuns()
    } catch (err) {
      setError(apiError(err))
      setConfirmOpen(false)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-paper">Billing</h1>
        <p className="mt-1 text-sm text-faint">
          Preview the day, run the idempotent batch, then work the invoices it produced.
        </p>
      </header>

      <ErrorBox message={error} />

      <Tabs
        tabs={[
          { id: 'day', label: 'Billing day' },
          { id: 'runs', label: 'Runs', count: runCount || undefined },
          { id: 'invoices', label: 'Invoices' },
          { id: 'payments', label: 'Payments' },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'day' && (
        <div className="space-y-5">
          <Card
            title="What would tonight bill?"
            subtitle="A dry run writes nothing. It reports due periods, including periods of terms that already ended."
            actions={
              <div className="flex flex-wrap items-end gap-2">
                <Field label="Business date">
                  <TextInput
                    type="date"
                    value={on}
                    onChange={(event) => {
                      setOn(event.target.value)
                      setPreview(null)
                      setResult(null)
                    }}
                    className="w-40"
                  />
                </Field>
                <Button variant="secondary" onClick={runPreview} disabled={running}>
                  {running && !preview ? 'Scanning…' : 'Preview'}
                </Button>
                <Button onClick={() => setConfirmOpen(true)} disabled={running}>
                  Run billing
                </Button>
              </div>
            }
          >
            {!preview && !result && (
              <EmptyState
                title="No preview yet"
                hint="Pick a date and press Preview to see exactly what the batch would invoice."
              />
            )}

            {preview && (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Badge tone="indigo">{preview.invoices} invoice(s)</Badge>
                  <Badge>{preview.subscriptions} subscription(s)</Badge>
                  <Badge tone={preview.missed_periods ? 'amber' : 'slate'}>
                    {preview.missed_periods} missed period(s)
                  </Badge>
                  {preview.problems?.length > 0 && (
                    <Badge tone="rose">{preview.problems.length} problem(s)</Badge>
                  )}
                </div>

                {preview.missed_periods > 0 && (
                  <p className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
                    {preview.missed_periods} due period(s) belong to terms that already ended.
                    Running the batch still bills them — that is revenue waiting, not a mistake.
                  </p>
                )}

                {preview.problems?.length > 0 && (
                  <div className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-xs text-bad">
                    {preview.problems.map((problem, index) => (
                      <p key={index}>
                        <span className="font-medium">{problem.subscription}</span>: {problem.error}
                      </p>
                    ))}
                  </div>
                )}

                <Table>
                  <thead>
                    <tr>
                      <Th>Subscription</Th>
                      <Th>Customer</Th>
                      <Th>Period</Th>
                      <Th>Estimated subtotal</Th>
                      <Th>Term</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.items.length === 0 && (
                      <EmptyRow colSpan={5}>Nothing is due on this date.</EmptyRow>
                    )}
                    {preview.items.map((item, index) => (
                      <Tr key={index}>
                        <Td className="font-medium text-paper">{item.subscription}</Td>
                        <Td>{item.customer}</Td>
                        <Td className="whitespace-nowrap text-faint">
                          {dateOnly(item.period_start)} → {dateOnly(item.period_end)}
                        </Td>
                        <Td>{money(item.estimated_subtotal)}</Td>
                        <Td>
                          <Badge tone={item.term_ended ? 'amber' : 'emerald'}>
                            {item.term_ended ? 'Ended' : 'Running'}
                          </Badge>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
                {preview.truncated && (
                  <p className="text-xs text-faint">
                    Showing the first {preview.items.length} items.
                  </p>
                )}
              </div>
            )}

            {result && (
              <div className="space-y-3">
                <p className="text-sm text-muted">
                  Billing run #{result.id} finished on {dateOnly(result.ran_on)}.
                </p>
                <RunReport run={result} />
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === 'runs' && (
        <Card title="Billing runs" subtitle="Every attempt is audited, including the failures." bodyClassName="pb-2">
          {runsLoading ? (
            <Loading />
          ) : (
            <>
              <Table>
                <thead>
                  <tr>
                    <Th>Run</Th>
                    <Th>Date</Th>
                    <Th>Billed</Th>
                    <Th>Skipped</Th>
                    <Th>Failed</Th>
                    <Th>Invoices</Th>
                    <Th>Finished</Th>
                  </tr>
                </thead>
                <tbody>
                  {runs.length === 0 && <EmptyRow colSpan={7}>No billing run yet.</EmptyRow>}
                  {runs.map((run) => (
                    <Tr key={run.id} onClick={() => setSelectedRun(run)}>
                      <Td className="font-medium text-paper">#{run.id}</Td>
                      <Td>{dateOnly(run.ran_on)}</Td>
                      <Td>{run.billed_count}</Td>
                      <Td>{run.skipped_count}</Td>
                      <Td>
                        <Badge tone={run.failed_count ? 'rose' : 'slate'}>{run.failed_count}</Badge>
                      </Td>
                      <Td>{run.invoice_count}</Td>
                      <Td className="text-faint">{dateTime(run.finished_at)}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
              <Pagination
                page={runPage}
                pageSize={15}
                count={runCount}
                onPage={setRunPage}
                busy={runsLoading}
              />
            </>
          )}
        </Card>
      )}

      {tab === 'invoices' && <InvoiceBrowser />}

      {tab === 'payments' && <PaymentsLedger />}

      <ConfirmModal
        open={confirmOpen}
        title="Run the billing day"
        message={`Bill every due period on ${on}. The batch is idempotent: periods already invoiced are skipped, and a bad record cannot abort the rest.`}
        confirmLabel="Run billing"
        tone="primary"
        busy={running}
        onConfirm={runBilling}
        onClose={() => setConfirmOpen(false)}
      />

      <Modal
        open={selectedRun !== null}
        wide
        title={selectedRun ? `Billing run #${selectedRun.id}` : 'Billing run'}
        subtitle={selectedRun ? `${dateOnly(selectedRun.ran_on)} · finished ${dateTime(selectedRun.finished_at)}` : ''}
        onClose={() => setSelectedRun(null)}
      >
        {selectedRun && <RunReport run={selectedRun} />}
      </Modal>
    </div>
  )
}
