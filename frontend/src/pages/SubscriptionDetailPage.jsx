import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Badge, { StageBadge, StatusBadge } from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Field, FormGrid, Select, TextInput } from '../components/ui/Form'
import Modal from '../components/ui/Modal'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateOnly, money, todayISO } from '../lib/format'

const ACTION_LABELS = {
  'send-quotation': 'Send quotation',
  confirm: 'Confirm',
  activate: 'Activate',
  close: 'Close',
  renew: 'Renew',
  pause: 'Pause',
  resume: 'Resume',
}

export default function SubscriptionDetailPage() {
  const { id } = useParams()
  const { isStaff } = useAuth()
  const [subscription, setSubscription] = useState(null)
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')

  const [products, setProducts] = useState([])
  const [taxes, setTaxes] = useState([])

  const [activateOpen, setActivateOpen] = useState(false)
  const [activateForm, setActivateForm] = useState({ start_date: '', expiry_date: '' })
  const [closeOpen, setCloseOpen] = useState(false)
  const [closeForm, setCloseForm] = useState({ reason: 'Closed by operator', on: '' })
  const [pauseOpen, setPauseOpen] = useState(false)
  const [pauseForm, setPauseForm] = useState({ on: '' })
  const [lineForm, setLineForm] = useState({ product: '', quantity: 1, tax_rule: '' })
  const [termForm, setTermForm] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get(`/subscriptions/${id}/`)
      setSubscription(data)
      setTermForm({
        start_date: data.start_date,
        expiry_date: data.expiry_date,
        payment_terms_days: data.payment_terms_days,
      })
      const invoiceRes = await api.get('/invoices/', {
        params: { subscription: id, page_size: 50 },
      })
      setInvoices(invoiceRes.data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!isStaff) return
    const loadReference = async () => {
      try {
        const [productRes, taxRes] = await Promise.all([
          api.get('/products/', { params: { page_size: 200 } }),
          api.get('/tax-rules/', { params: { page_size: 200 } }),
        ])
        setProducts(productRes.data.results ?? [])
        setTaxes(taxRes.data.results ?? [])
      } catch {
        // Reference data is a convenience; the page still works without it.
      }
    }
    loadReference()
  }, [isStaff])

  const run = async (label, request) => {
    setBusy(label)
    setError('')
    setNotice('')
    try {
      await request()
      await load()
      setNotice(`${ACTION_LABELS[label] ?? label} done.`)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setBusy('')
    }
  }

  const stage = subscription?.stage
  const canEditLines = stage === 'draft' || stage === 'quotation'

  const actions = useMemo(() => {
    if (!subscription || !isStaff) return []
    const list = []
    if (stage === 'draft') list.push(['send-quotation'])
    if (stage === 'quotation') list.push(['confirm'])
    if (stage === 'confirmed') list.push(['activate'])
    if (stage === 'active') {
      list.push(['renew'])
      if (subscription.is_paused) list.push(['resume'])
      else list.push(['pause'])
      list.push(['close'])
    }
    if (['draft', 'quotation', 'confirmed'].includes(stage)) list.push(['close'])
    return list
  }, [subscription, stage, isStaff])

  const onAction = (action) => {
    if (action === 'activate') {
      setActivateForm({
        start_date: subscription.start_date,
        expiry_date: subscription.expiry_date,
      })
      setActivateOpen(true)
      return
    }
    if (action === 'close') {
      setCloseForm({ reason: 'Closed by operator', on: todayISO() })
      setCloseOpen(true)
      return
    }
    if (action === 'pause') {
      setPauseForm({ on: todayISO() })
      setPauseOpen(true)
      return
    }
    if (action === 'resume') {
      run('resume', () => api.post(`/subscriptions/${id}/resume/`, { on: todayISO() }))
      return
    }
    run(action, () => api.post(`/subscriptions/${id}/${action}/`))
  }

  const submitActivate = async (event) => {
    event.preventDefault()
    await run('activate', () =>
      api.post(`/subscriptions/${id}/activate/`, activateForm),
    )
    setActivateOpen(false)
  }

  const submitClose = async (event) => {
    event.preventDefault()
    await run('close', () => api.post(`/subscriptions/${id}/close/`, closeForm))
    setCloseOpen(false)
  }

  const submitPause = async (event) => {
    event.preventDefault()
    await run('pause', () => api.post(`/subscriptions/${id}/pause/`, pauseForm))
    setPauseOpen(false)
  }

  const addLine = async (event) => {
    event.preventDefault()
    await run('line', () =>
      api.post(`/subscriptions/${id}/lines/`, {
        product: Number(lineForm.product),
        quantity: Number(lineForm.quantity),
        tax_rule: lineForm.tax_rule ? Number(lineForm.tax_rule) : undefined,
      }),
    )
    setLineForm({ product: '', quantity: 1, tax_rule: '' })
  }

  const removeLine = async (lineId) => {
    await run('remove line', () =>
      api.delete(`/subscriptions/${id}/lines/${lineId}/`),
    )
  }

  const saveTerm = async (event) => {
    event.preventDefault()
    await run('update term', () => api.patch(`/subscriptions/${id}/`, termForm))
  }

  if (loading && !subscription) return <Loading label="Loading subscription…" />
  if (!subscription) return <ErrorBox message={error || 'Subscription not found.'} onRetry={load} />

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Link to="/subscriptions" className="text-sm text-slate-400 hover:text-slate-600">
              ← Subscriptions
            </Link>
          </div>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold text-slate-900">
            {subscription.number}
            <StageBadge stage={subscription.stage} label={subscription.stage_display} />
            {subscription.is_paused && <Badge tone="amber">Paused</Badge>}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {subscription.customer_name} · {subscription.plan_name} ·{' '}
            {subscription.billing_frequency}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {actions.map(([action]) => (
            <Button
              key={action}
              size="sm"
              variant={action === 'close' ? 'danger' : action === 'renew' ? 'secondary' : 'primary'}
              onClick={() => onAction(action)}
              disabled={Boolean(busy)}
            >
              {busy === action ? 'Working…' : ACTION_LABELS[action]}
            </Button>
          ))}
        </div>
      </header>

      <ErrorBox message={error} onRetry={load} />
      {notice && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Contract" className="lg:col-span-2">
          <form onSubmit={saveTerm} className="space-y-4">
            <FormGrid columns={3}>
              <Field label="Start date">
                <TextInput
                  type="date"
                  value={termForm?.start_date ?? ''}
                  onChange={(event) =>
                    setTermForm({ ...termForm, start_date: event.target.value })
                  }
                  disabled={!isStaff}
                />
              </Field>
              <Field label="Expiry date">
                <TextInput
                  type="date"
                  value={termForm?.expiry_date ?? ''}
                  onChange={(event) =>
                    setTermForm({ ...termForm, expiry_date: event.target.value })
                  }
                  disabled={!isStaff}
                />
              </Field>
              <Field label="Payment terms (days)">
                <TextInput
                  type="number"
                  min="0"
                  value={termForm?.payment_terms_days ?? 0}
                  onChange={(event) =>
                    setTermForm({ ...termForm, payment_terms_days: event.target.value })
                  }
                  disabled={!isStaff}
                />
              </Field>
            </FormGrid>
            {isStaff && (
              <div className="flex justify-end">
                <Button type="submit" size="sm" variant="secondary" disabled={Boolean(busy)}>
                  Save term
                </Button>
              </div>
            )}
          </form>
        </Card>

        <Card title="Totals">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-500">Subtotal</dt>
              <dd className="font-medium">{money(subscription.subtotal)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Tax</dt>
              <dd className="font-medium">{money(subscription.tax_total)}</dd>
            </div>
            <div className="flex justify-between border-t border-slate-100 pt-2">
              <dt className="font-medium text-slate-700">Total</dt>
              <dd className="font-semibold text-slate-900">{money(subscription.total)}</dd>
            </div>
          </dl>
        </Card>
      </div>

      <Card
        title="Lines"
        subtitle="Prices and taxes are snapshotted onto the line when it is added."
      >
        <Table>
          <thead>
            <tr>
              <Th>Product</Th>
              <Th>Variant</Th>
              <Th>Qty</Th>
              <Th>Unit price</Th>
              <Th>Tax</Th>
              <Th>Amount</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {subscription.lines.length === 0 && (
              <EmptyRow colSpan={7}>No lines yet — a quotation needs at least one.</EmptyRow>
            )}
            {subscription.lines.map((line) => (
              <Tr key={line.id}>
                <Td className="font-medium text-slate-800">{line.product_name}</Td>
                <Td>{line.variant_label || <span className="text-slate-300">—</span>}</Td>
                <Td>{line.quantity}</Td>
                <Td>{money(line.unit_price)}</Td>
                <Td>{line.tax_rate ? `${Number(line.tax_rate).toFixed(2)}%` : '—'}</Td>
                <Td>{money(line.amount)}</Td>
                <Td className="text-right">
                  {isStaff && canEditLines && (
                    <Button
                      size="xs"
                      variant="ghost"
                      onClick={() => removeLine(line.id)}
                      disabled={Boolean(busy)}
                    >
                      Remove
                    </Button>
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>

        {isStaff && canEditLines && (
          <form onSubmit={addLine} className="mt-4 grid gap-2 sm:grid-cols-[2fr_80px_1fr_auto]">
            <Select
              required
              value={lineForm.product}
              onChange={(event) => setLineForm({ ...lineForm, product: event.target.value })}
            >
              <option value="">Product…</option>
              {products.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name} · {money(product.sales_price)}
                </option>
              ))}
            </Select>
            <TextInput
              type="number"
              min="1"
              value={lineForm.quantity}
              onChange={(event) => setLineForm({ ...lineForm, quantity: event.target.value })}
            />
            <Select
              value={lineForm.tax_rule}
              onChange={(event) => setLineForm({ ...lineForm, tax_rule: event.target.value })}
            >
              <option value="">No tax</option>
              {taxes.map((tax) => (
                <option key={tax.id} value={tax.id}>
                  {tax.name} ({Number(tax.rate).toFixed(0)}%)
                </option>
              ))}
            </Select>
            <Button type="submit" size="sm" disabled={Boolean(busy)}>
              Add line
            </Button>
          </form>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Pause history" subtitle="Billing drops every period that overlaps a span.">
          <Table>
            <thead>
              <tr>
                <Th>Started</Th>
                <Th>Ended</Th>
                <Th>State</Th>
              </tr>
            </thead>
            <tbody>
              {subscription.pause_periods.length === 0 && (
                <EmptyRow colSpan={3}>Never paused.</EmptyRow>
              )}
              {subscription.pause_periods.map((span) => (
                <Tr key={span.id}>
                  <Td>{dateOnly(span.started_on)}</Td>
                  <Td>{span.ended_on ? dateOnly(span.ended_on) : '—'}</Td>
                  <Td>
                    <Badge tone={span.ended_on ? 'slate' : 'amber'}>
                      {span.ended_on ? 'Closed' : 'Open'}
                    </Badge>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card
          title="Invoices"
          subtitle="Periods already billed for this subscription."
          actions={
            <Link to="/billing" className="text-xs font-medium text-indigo-600">
              Billing day →
            </Link>
          }
        >
          <Table>
            <thead>
              <tr>
                <Th>Number</Th>
                <Th>Period</Th>
                <Th>Status</Th>
                <Th>Total</Th>
              </tr>
            </thead>
            <tbody>
              {invoices.length === 0 && <EmptyRow colSpan={4}>No invoices yet.</EmptyRow>}
              {invoices.map((invoice) => (
                <Tr key={invoice.id}>
                  <Td className="font-medium text-slate-800">{invoice.number}</Td>
                  <Td className="whitespace-nowrap text-slate-500">
                    {dateOnly(invoice.period_start)} → {dateOnly(invoice.period_end)}
                  </Td>
                  <Td>
                    <StatusBadge status={invoice.status} />
                  </Td>
                  <Td>{money(invoice.total)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      </div>

      <Modal
        open={activateOpen}
        title="Activate subscription"
        subtitle="The term may be adjusted here; expiry must stay after start."
        onClose={() => setActivateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setActivateOpen(false)} disabled={Boolean(busy)}>
              Cancel
            </Button>
            <Button type="submit" form="activate-form" disabled={Boolean(busy)}>
              {busy === 'activate' ? 'Activating…' : 'Activate'}
            </Button>
          </>
        }
      >
        <form id="activate-form" onSubmit={submitActivate} className="space-y-4">
          <Field label="Start date">
            <TextInput
              type="date"
              required
              value={activateForm.start_date}
              onChange={(event) =>
                setActivateForm({ ...activateForm, start_date: event.target.value })
              }
            />
          </Field>
          <Field label="Expiry date">
            <TextInput
              type="date"
              required
              value={activateForm.expiry_date}
              onChange={(event) =>
                setActivateForm({ ...activateForm, expiry_date: event.target.value })
              }
            />
          </Field>
        </form>
      </Modal>

      <Modal
        open={closeOpen}
        title="Close subscription"
        subtitle="Closes the term. Early close may be refused by the plan."
        onClose={() => setCloseOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCloseOpen(false)} disabled={Boolean(busy)}>
              Cancel
            </Button>
            <Button type="submit" form="close-form" variant="danger" disabled={Boolean(busy)}>
              {busy === 'close' ? 'Closing…' : 'Close subscription'}
            </Button>
          </>
        }
      >
        <form id="close-form" onSubmit={submitClose} className="space-y-4">
          <Field label="Reason">
            <TextInput
              required
              value={closeForm.reason}
              onChange={(event) => setCloseForm({ ...closeForm, reason: event.target.value })}
            />
          </Field>
          <Field label="Business date">
            <TextInput
              type="date"
              value={closeForm.on}
              onChange={(event) => setCloseForm({ ...closeForm, on: event.target.value })}
            />
          </Field>
        </form>
      </Modal>

      <Modal
        open={pauseOpen}
        title="Pause subscription"
        subtitle="Pausing stops billing: every period overlapping the pause is dropped."
        onClose={() => setPauseOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPauseOpen(false)} disabled={Boolean(busy)}>
              Cancel
            </Button>
            <Button type="submit" form="pause-form" disabled={Boolean(busy)}>
              {busy === 'pause' ? 'Pausing…' : 'Pause'}
            </Button>
          </>
        }
      >
        <form id="pause-form" onSubmit={submitPause} className="space-y-4">
          <Field label="Paused from">
            <TextInput
              type="date"
              required
              value={pauseForm.on}
              onChange={(event) => setPauseForm({ on: event.target.value })}
            />
          </Field>
        </form>
      </Modal>
    </div>
  )
}
