import { useCallback, useEffect, useState } from 'react'
import Badge, { StatusBadge } from '../ui/Badge'
import Button from '../ui/Button'
import Card from '../ui/Card'
import { ErrorBox, Loading } from '../ui/Feedback'
import { Field, FormGrid, Select, TextInput } from '../ui/Form'
import Modal from '../ui/Modal'
import { EmptyRow, Table, Td, Th, Tr } from '../ui/Table'
import Pagination from '../Pagination'
import api, { apiError } from '../../lib/api'
import { dateOnly, dateTime, money, titleize, todayISO } from '../../lib/format'

const STATUSES = ['draft', 'confirmed', 'paid', 'cancelled']
const METHODS = ['bank_transfer', 'card', 'cash', 'check', 'other']

const emptyPayment = { amount: '', method: 'bank_transfer', paid_on: '', reference: '', note: '' }

export default function InvoiceBrowser() {
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [payment, setPayment] = useState(emptyPayment)
  const [paymentError, setPaymentError] = useState('')

  const pageSize = 15

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/invoices/', {
        params: { page, page_size: pageSize, status: status || undefined },
      })
      setRows(data.results ?? [])
      setCount(data.count ?? 0)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [page, status])

  useEffect(() => {
    load()
  }, [load])

  const openInvoice = async (invoice) => {
    setDetail({ ...invoice })
    setDetailLoading(true)
    setPaymentError('')
    try {
      const { data } = await api.get(`/invoices/${invoice.id}/`)
      setDetail(data)
      setPayment({
        ...emptyPayment,
        amount: data.amount_due,
        paid_on: todayISO(),
      })
    } catch (err) {
      setError(apiError(err))
    } finally {
      setDetailLoading(false)
    }
  }

  const refreshDetail = async (invoiceId) => {
    const { data } = await api.get(`/invoices/${invoiceId}/`)
    setDetail(data)
    setPayment((current) => ({ ...current, amount: data.amount_due }))
  }

  const act = async (action, body = {}) => {
    setBusy(action)
    setError('')
    try {
      await api.post(`/invoices/${detail.id}/${action}/`, body)
      await refreshDetail(detail.id)
      await load()
    } catch (err) {
      setError(apiError(err))
    } finally {
      setBusy('')
    }
  }

  const recordPayment = async (event) => {
    event.preventDefault()
    setBusy('payment')
    setPaymentError('')
    try {
      await api.post('/payments/', {
        invoice: detail.id,
        amount: payment.amount,
        method: payment.method,
        paid_on: payment.paid_on || undefined,
        reference: payment.reference || undefined,
        note: payment.note || undefined,
      })
      await refreshDetail(detail.id)
      await load()
    } catch (err) {
      setPaymentError(apiError(err))
    } finally {
      setBusy('')
    }
  }

  const removePayment = async (paymentId) => {
    setBusy(`payment-${paymentId}`)
    setPaymentError('')
    try {
      await api.delete(`/payments/${paymentId}/`)
      await refreshDetail(detail.id)
      await load()
    } catch (err) {
      setPaymentError(apiError(err))
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-4">
      <ErrorBox message={error} onRetry={load} />

      <Card
        title="Invoices"
        subtitle="Click a row to open the ledger, issue it or record a payment."
        actions={
          <Select
            value={status}
            onChange={(event) => {
              setPage(1)
              setStatus(event.target.value)
            }}
            className="w-40"
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {titleize(value)}
              </option>
            ))}
          </Select>
        }
        bodyClassName="pb-2"
      >
        {loading ? (
          <Loading />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Number</Th>
                  <Th>Customer</Th>
                  <Th>Subscription</Th>
                  <Th>Period</Th>
                  <Th>Status</Th>
                  <Th>Total</Th>
                  <Th>Due</Th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && <EmptyRow colSpan={7}>No invoices match.</EmptyRow>}
                {rows.map((invoice) => (
                  <Tr key={invoice.id} onClick={() => openInvoice(invoice)}>
                    <Td className="font-medium text-primary">{invoice.number}</Td>
                    <Td>{invoice.customer_name}</Td>
                    <Td>{invoice.subscription_number}</Td>
                    <Td className="whitespace-nowrap text-secondary">
                      {dateOnly(invoice.period_start)} → {dateOnly(invoice.period_end)}
                    </Td>
                    <Td>
                      <StatusBadge status={invoice.status} />
                    </Td>
                    <Td>{money(invoice.total)}</Td>
                    <Td>{money(invoice.amount_due)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={pageSize} count={count} onPage={setPage} busy={loading} />
          </>
        )}
      </Card>

      <Modal
        open={detail !== null}
        wide
        title={detail ? `Invoice ${detail.number}` : 'Invoice'}
        subtitle={detail ? `${detail.customer_name} · ${detail.subscription_number}` : ''}
        onClose={() => setDetail(null)}
        footer={
          detail && (
            <>
              {detail.status === 'draft' && (
                <Button
                  variant="secondary"
                  onClick={() => act('confirm')}
                  disabled={Boolean(busy)}
                >
                  {busy === 'confirm' ? 'Issuing…' : 'Issue invoice'}
                </Button>
              )}
              {['draft', 'confirmed'].includes(detail.status) && (
                <Button
                  variant="secondary"
                  onClick={() => act('send')}
                  disabled={Boolean(busy)}
                >
                  {busy === 'send' ? 'Sending…' : 'Mark sent'}
                </Button>
              )}
              {['draft', 'confirmed'].includes(detail.status) && (
                <Button
                  variant="secondary"
                  onClick={() => act('mark-printed')}
                  disabled={Boolean(busy)}
                >
                  Mark printed
                </Button>
              )}
              {detail.status !== 'cancelled' && (
                <Button
                  variant="danger"
                  onClick={() => act('cancel', { reason: 'Cancelled from console' })}
                  disabled={Boolean(busy)}
                >
                  {busy === 'cancel' ? 'Cancelling…' : 'Cancel invoice'}
                </Button>
              )}
              <Button variant="ghost" onClick={() => setDetail(null)}>
                Close
              </Button>
            </>
          )
        }
      >
        {detailLoading ? (
          <Loading label="Loading invoice…" />
        ) : detail ? (
          <div className="space-y-4">
            <ErrorBox message={error} />
            <div className="grid gap-3 sm:grid-cols-4">
              <div>
                <p className="text-xs text-muted">Status</p>
                <StatusBadge status={detail.status} label={detail.status_display} />
              </div>
              <div>
                <p className="text-xs text-muted">Period</p>
                <p className="text-sm text-secondary">
                  {dateOnly(detail.period_start)} → {dateOnly(detail.period_end)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted">Issued / due</p>
                <p className="text-sm text-secondary">
                  {dateOnly(detail.issued_at)} / {dateOnly(detail.due_date)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted">Overdue</p>
                <Badge tone={detail.is_overdue ? 'rose' : 'emerald'}>
                  {detail.is_overdue ? 'Yes' : 'No'}
                </Badge>
              </div>
            </div>

            <Table>
              <thead>
                <tr>
                  <Th>Description</Th>
                  <Th>Qty</Th>
                  <Th>Unit</Th>
                  <Th>Amount</Th>
                </tr>
              </thead>
              <tbody>
                {detail.lines.length === 0 && <EmptyRow colSpan={4}>No lines.</EmptyRow>}
                {detail.lines.map((line) => (
                  <Tr key={line.id}>
                    <Td>{line.description}</Td>
                    <Td>{line.quantity}</Td>
                    <Td>{money(line.unit_price)}</Td>
                    <Td>{money(line.amount)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>

            <div className="grid gap-2 rounded-lg bg-sunken px-4 py-3 text-sm sm:grid-cols-4">
              <div>
                <p className="text-xs text-muted">Subtotal</p>
                <p>{money(detail.subtotal)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Discount</p>
                <p>-{money(detail.discount_total)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Tax</p>
                <p>{money(detail.tax_total)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Total / paid / due</p>
                <p className="font-medium">
                  {money(detail.total)} / {money(detail.amount_paid)} /{' '}
                  {money(detail.amount_due)}
                </p>
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-semibold text-secondary">Payments</h3>
              <Table>
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>Method</Th>
                    <Th>Reference</Th>
                    <Th>Amount</Th>
                    <Th>Recorded by</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {detail.payments.length === 0 && (
                    <EmptyRow colSpan={6}>No payments recorded.</EmptyRow>
                  )}
                  {detail.payments.map((entry) => (
                    <Tr key={entry.id}>
                      <Td>{dateOnly(entry.paid_on)}</Td>
                      <Td>{titleize(entry.method)}</Td>
                      <Td>{entry.reference || '—'}</Td>
                      <Td>{money(entry.amount)}</Td>
                      <Td className="text-secondary">{entry.recorded_by_email || '—'}</Td>
                      <Td className="text-right">
                        {detail.status !== 'cancelled' && (
                          <Button
                            size="xs"
                            variant="ghost"
                            onClick={() => removePayment(entry.id)}
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
            </div>

            {detail.status !== 'cancelled' && Number(detail.amount_due) > 0 && (
              <form onSubmit={recordPayment} className="space-y-3 rounded-lg border border-line p-4">
                <h3 className="text-sm font-semibold text-secondary">Record a payment</h3>
                <ErrorBox message={paymentError} />
                <FormGrid columns={3}>
                  <Field label="Amount">
                    <TextInput
                      type="number"
                      step="0.01"
                      min="0.01"
                      required
                      value={payment.amount}
                      onChange={(event) => setPayment({ ...payment, amount: event.target.value })}
                    />
                  </Field>
                  <Field label="Method">
                    <Select
                      value={payment.method}
                      onChange={(event) => setPayment({ ...payment, method: event.target.value })}
                    >
                      {METHODS.map((method) => (
                        <option key={method} value={method}>
                          {titleize(method)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Paid on">
                    <TextInput
                      type="date"
                      value={payment.paid_on}
                      onChange={(event) => setPayment({ ...payment, paid_on: event.target.value })}
                    />
                  </Field>
                  <Field label="Reference" className="sm:col-span-2">
                    <TextInput
                      value={payment.reference}
                      onChange={(event) => setPayment({ ...payment, reference: event.target.value })}
                    />
                  </Field>
                  <Field label="Note">
                    <TextInput
                      value={payment.note}
                      onChange={(event) => setPayment({ ...payment, note: event.target.value })}
                    />
                  </Field>
                </FormGrid>
                <div className="flex justify-end">
                  <Button type="submit" size="sm" disabled={busy === 'payment'}>
                    {busy === 'payment' ? 'Recording…' : 'Record payment'}
                  </Button>
                </div>
              </form>
            )}

            <p className="text-xs text-muted">Created {dateTime(detail.created_at)}</p>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
