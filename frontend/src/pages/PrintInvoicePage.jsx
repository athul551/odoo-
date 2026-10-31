import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import Button from '../components/ui/Button'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import api, { apiError } from '../lib/api'
import { dateOnly, money, titleize } from '../lib/format'

export default function PrintInvoicePage() {
  const { id } = useParams()
  const [invoice, setInvoice] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get(`/invoices/${id}/`)
      setInvoice(data)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="dark-page grid min-h-screen place-items-center">
        <Loading label="Preparing the invoice…" />
      </div>
    )
  }

  if (error || !invoice) {
    return (
      <div className="dark-page grid min-h-screen place-items-center px-6">
        <ErrorBox message={error || 'Invoice not found.'} onRetry={load} />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-ink-950 px-6 py-10 print:bg-white print:p-0">
      <div className="mx-auto mb-4 flex max-w-3xl justify-end gap-2 print:hidden">
        <Button variant="secondary" onClick={() => window.close()}>
          Close
        </Button>
        <Button onClick={() => window.print()}>Print / Save PDF</Button>
      </div>

      <article className="mx-auto max-w-3xl bg-white px-12 py-10 text-slate-900 print:max-w-none print:px-0 print:py-0">
        <header className="flex items-start justify-between border-b border-slate-300 pb-6">
          <div>
            <p className="text-2xl font-bold tracking-tight text-indigo-700">Brightloop</p>
            <p className="mt-1 text-xs text-slate-500">Subscription management</p>
          </div>
          <div className="text-right">
            <p className="text-lg font-semibold">{invoice.number}</p>
            <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">
              {invoice.status_display ?? titleize(invoice.status)}
            </p>
          </div>
        </header>

        <section className="mt-6 grid grid-cols-2 gap-6 text-sm">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-400">Billed to</p>
            <p className="mt-1 font-medium">{invoice.customer_name}</p>
          </div>
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-slate-400">Period</p>
            <p className="mt-1">
              {dateOnly(invoice.period_start)} → {dateOnly(invoice.period_end)}
            </p>
            <p className="mt-2 text-xs uppercase tracking-wide text-slate-400">Due</p>
            <p>{dateOnly(invoice.due_date)}</p>
          </div>
        </section>

        <table className="mt-8 w-full text-sm">
          <thead>
            <tr className="border-b border-slate-300 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2">Description</th>
              <th className="py-2 text-right">Qty</th>
              <th className="py-2 text-right">Unit</th>
              <th className="py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {invoice.lines.map((line) => (
              <tr key={line.id} className="border-b border-slate-100">
                <td className="py-2">{line.description}</td>
                <td className="py-2 text-right">{line.quantity}</td>
                <td className="py-2 text-right">{money(line.unit_price)}</td>
                <td className="py-2 text-right">{money(line.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <section className="mt-6 ml-auto w-64 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-500">Subtotal</span>
            <span>{money(invoice.subtotal)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Discount</span>
            <span>-{money(invoice.discount_total)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Tax</span>
            <span>{money(invoice.tax_total)}</span>
          </div>
          <div className="flex justify-between border-t border-slate-300 pt-1 font-semibold">
            <span>Total</span>
            <span>{money(invoice.total)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Paid</span>
            <span>{money(invoice.amount_paid)}</span>
          </div>
          <div className="flex justify-between font-semibold">
            <span>Amount due</span>
            <span>{money(invoice.amount_due)}</span>
          </div>
        </section>

        {invoice.payments.length > 0 && (
          <section className="mt-8">
            <h2 className="text-xs uppercase tracking-wide text-slate-400">Payments</h2>
            <ul className="mt-2 space-y-1 text-sm">
              {invoice.payments.map((payment) => (
                <li key={payment.id} className="flex justify-between">
                  <span>
                    {dateOnly(payment.paid_on)} · {titleize(payment.method)}
                    {payment.reference ? ` · ${payment.reference}` : ''}
                  </span>
                  <span>{money(payment.amount)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <footer className="mt-10 border-t border-slate-200 pt-4 text-xs text-slate-400">
          Brightloop · invoice {invoice.number} · generated {dateOnly(new Date().toISOString())}
        </footer>
      </article>
    </div>
  )
}
