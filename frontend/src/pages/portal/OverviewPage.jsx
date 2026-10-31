import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DarkTable, Empty, Kpi, Panel, StagePill, StatusPill, Td, Th } from '../../components/portal/ui'
import api, { apiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { dateOnly, money } from '../../lib/format'

export default function PortalOverviewPage() {
  const { user } = useAuth()
  const [subscriptions, setSubscriptions] = useState([])
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [subs, invs] = await Promise.all([
        api.get('/subscriptions/', { params: { page_size: 200 } }),
        api.get('/invoices/', { params: { page_size: 200 } }),
      ])
      setSubscriptions(subs.data.results ?? [])
      setInvoices(invs.data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const active = subscriptions.filter((sub) => sub.stage === 'active' && !sub.is_paused)
  const paused = subscriptions.filter((sub) => sub.stage === 'active' && sub.is_paused)
  const open = invoices.filter((invoice) => invoice.status === 'confirmed')
  const due = open.reduce((sum, invoice) => sum + Number(invoice.amount_due ?? 0), 0)
  const nextExpiry = active
    .map((sub) => sub.expiry_date)
    .filter(Boolean)
    .sort()[0]

  const firstName = user?.first_name || 'there'

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-faint">
          {user?.customer?.name ?? 'Your organization'}
        </p>
        <h1 className="mt-2 text-4xl font-light tracking-tight text-paper">
          Welcome, {firstName}.
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Everything Brightloop bills you for, in one place. Invoices are issued by a billing run
          you can ask us to preview first — nothing is charged silently.
        </p>
      </header>

      {error && (
        <div className="rounded-panel border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-faint">Loading your account…</p>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi
              label="Active subscriptions"
              value={active.length}
              hint={paused.length ? `${paused.length} paused` : 'All running'}
            />
            <Kpi
              label="Open invoices"
              value={open.length}
              hint={open.length ? 'Awaiting payment' : 'Nothing outstanding'}
            />
            <Kpi label="Amount due" value={money(due)} hint="Confirmed invoices only" />
            <Kpi
              label="Next renewal"
              value={nextExpiry ? dateOnly(nextExpiry) : '—'}
              hint={nextExpiry ? 'Earliest term end' : 'No dated term yet'}
            />
          </div>

          {subscriptions.length === 0 && invoices.length === 0 ? (
            <Panel title="Your account is ready">
              <p className="max-w-2xl text-sm leading-relaxed text-muted">
                No subscriptions yet. Your account manager sets them up on this organization; as
                soon as one is activated it appears here with its invoices and payment status.
              </p>
              <p className="mt-4 text-sm text-faint">
                Need something changed? Reply to your onboarding email and quote{' '}
                <span className="font-mono text-muted">{user?.customer?.name ?? 'your organization'}</span>.
              </p>
            </Panel>
          ) : (
            <>
              <Panel
                title="Recent invoices"
                subtitle="Newest periods first"
                actions={
                  <Link
                    to="/portal/invoices"
                    className="text-xs font-medium text-accent hover:text-accent-hover"
                  >
                    All invoices →
                  </Link>
                }
              >
                <DarkTable
                  head={
                    <>
                      <Th>Invoice</Th>
                      <Th>Period</Th>
                      <Th>Status</Th>
                      <Th className="text-right">Total</Th>
                      <Th className="text-right">Due</Th>
                    </>
                  }
                >
                  {invoices.length === 0 && (
                    <Empty colSpan={5} title="No invoices yet" hint="Billing has not run for your account." />
                  )}
                  {invoices.slice(0, 5).map((invoice) => (
                    <tr key={invoice.id}>
                      <Td className="font-mono text-xs text-paper">{invoice.number}</Td>
                      <Td className="whitespace-nowrap">
                        {dateOnly(invoice.period_start)} → {dateOnly(invoice.period_end)}
                      </Td>
                      <Td>
                        <StatusPill status={invoice.status} />
                      </Td>
                      <Td className="text-right text-paper">{money(invoice.total)}</Td>
                      <Td className="text-right">{money(invoice.amount_due)}</Td>
                    </tr>
                  ))}
                </DarkTable>
              </Panel>

              <Panel
                title="Your subscriptions"
                actions={
                  <Link
                    to="/portal/subscriptions"
                    className="text-xs font-medium text-accent hover:text-accent-hover"
                  >
                    Details →
                  </Link>
                }
              >
                <DarkTable
                  head={
                    <>
                      <Th>Number</Th>
                      <Th>Plan</Th>
                      <Th>Stage</Th>
                      <Th>Term</Th>
                      <Th className="text-right">Total</Th>
                    </>
                  }
                >
                  {subscriptions.length === 0 && (
                    <Empty colSpan={5} title="No subscriptions yet" />
                  )}
                  {subscriptions.slice(0, 5).map((subscription) => (
                    <tr key={subscription.id}>
                      <Td className="font-mono text-xs text-paper">{subscription.number}</Td>
                      <Td>{subscription.plan_name}</Td>
                      <Td>
                        <StagePill stage={subscription.stage} label={subscription.stage_display} />
                      </Td>
                      <Td className="whitespace-nowrap">
                        {dateOnly(subscription.start_date)} → {dateOnly(subscription.expiry_date)}
                      </Td>
                      <Td className="text-right text-paper">{money(subscription.total)}</Td>
                    </tr>
                  ))}
                </DarkTable>
              </Panel>
            </>
          )}
        </>
      )}
    </div>
  )
}
