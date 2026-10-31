import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Pagination from '../components/Pagination'
import Badge, { StageBadge } from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Field, FormGrid, Select, TextInput } from '../components/ui/Form'
import Modal from '../components/ui/Modal'
import api, { apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateOnly, money } from '../lib/format'

const STAGES = ['draft', 'quotation', 'confirmed', 'active', 'closed']

export default function SubscriptionsPage() {
  const { isStaff } = useAuth()
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [stage, setStage] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [customers, setCustomers] = useState([])
  const [plans, setPlans] = useState([])
  const [products, setProducts] = useState([])
  const [taxes, setTaxes] = useState([])

  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [form, setForm] = useState(null)

  const pageSize = 20

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/subscriptions/', {
        params: {
          page,
          page_size: pageSize,
          stage: stage || undefined,
          q: search || undefined,
        },
      })
      setRows(data.results ?? [])
      setCount(data.count ?? 0)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [page, stage, search])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const loadReference = async () => {
      try {
        const [customerRes, planRes, productRes, taxRes] = await Promise.all([
          api.get('/customers/', { params: { page_size: 200 } }),
          api.get('/plans/', { params: { page_size: 200, selectable: true } }),
          api.get('/products/', { params: { page_size: 200 } }),
          api.get('/tax-rules/', { params: { page_size: 200 } }),
        ])
        setCustomers(customerRes.data.results ?? [])
        setPlans(planRes.data.results ?? [])
        setProducts(productRes.data.results ?? [])
        setTaxes(taxRes.data.results ?? [])
      } catch {
        // The create form simply stays empty if reference data fails.
      }
    }
    if (isStaff) loadReference()
  }, [isStaff])

  const openCreate = () => {
    const today = new Date().toISOString().slice(0, 10)
    const nextYear = new Date()
    nextYear.setFullYear(nextYear.getFullYear() + 1)
    setForm({
      customer: '',
      plan: '',
      start_date: today,
      expiry_date: nextYear.toISOString().slice(0, 10),
      payment_terms_days: 30,
      lines: [{ product: '', quantity: 1, tax_rule: '' }],
    })
    setFormError('')
    setCreating(true)
  }

  const planOptions = useMemo(() => plans, [plans])

  const setLine = (index, key, value) => {
    setForm((current) => {
      const lines = current.lines.map((line, i) =>
        i === index ? { ...line, [key]: value } : line,
      )
      return { ...current, lines }
    })
  }

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const payload = {
        customer: Number(form.customer),
        plan: Number(form.plan),
        start_date: form.start_date,
        expiry_date: form.expiry_date || undefined,
        payment_terms_days: Number(form.payment_terms_days),
        lines: form.lines
          .filter((line) => line.product)
          .map((line) => ({
            product: Number(line.product),
            quantity: Number(line.quantity),
            tax_rule: line.tax_rule ? Number(line.tax_rule) : undefined,
          })),
      }
      const { data } = await api.post('/subscriptions/', payload)
      setCreating(false)
      setPage(1)
      await load()
      window.location.assign(`/subscriptions/${data.id}`)
    } catch (err) {
      setFormError(apiError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-paper">Subscriptions</h1>
          <p className="mt-1 text-sm text-faint">
            The contract lifecycle: draft → quotation → confirmed → active → closed.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select
            value={stage}
            onChange={(event) => {
              setPage(1)
              setStage(event.target.value)
            }}
            className="w-36"
          >
            <option value="">All stages</option>
            {STAGES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
          <TextInput
            value={search}
            onChange={(event) => {
              setPage(1)
              setSearch(event.target.value)
            }}
            placeholder="Search number or customer…"
            className="w-56"
          />
          {isStaff && <Button onClick={openCreate}>New subscription</Button>}
        </div>
      </header>

      <ErrorBox message={error} onRetry={load} />

      <Card bodyClassName="pb-2">
        {loading ? (
          <Loading />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Number</Th>
                  <Th>Customer</Th>
                  <Th>Plan</Th>
                  <Th>Stage</Th>
                  <Th>Term</Th>
                  <Th>Total</Th>
                  <Th>Invoices</Th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && <EmptyRow colSpan={7}>No subscriptions match.</EmptyRow>}
                {rows.map((subscription) => (
                  <Tr key={subscription.id}>
                    <Td>
                      <Link
                        to={`/subscriptions/${subscription.id}`}
                        className="font-medium text-accent hover:text-accent-hover"
                      >
                        {subscription.number}
                      </Link>
                      {subscription.is_paused && (
                        <Badge tone="amber" className="ml-2">
                          Paused
                        </Badge>
                      )}
                    </Td>
                    <Td>{subscription.customer_name}</Td>
                    <Td>
                      {subscription.plan_name}
                      <span className="ml-1 text-xs text-faint">
                        {subscription.billing_frequency}
                      </span>
                    </Td>
                    <Td>
                      <StageBadge stage={subscription.stage} label={subscription.stage_display} />
                    </Td>
                    <Td className="whitespace-nowrap text-faint">
                      {dateOnly(subscription.start_date)} → {dateOnly(subscription.expiry_date)}
                    </Td>
                    <Td>{money(subscription.total)}</Td>
                    <Td>
                      <Badge>{subscription.invoice_count ?? 0}</Badge>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            <Pagination page={page} pageSize={pageSize} count={count} onPage={setPage} busy={loading} />
          </>
        )}
      </Card>

      <Modal
        open={creating}
        wide
        title="New subscription"
        subtitle="Creates a Draft with its lines; move it through the stages on its page."
        onClose={() => setCreating(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreating(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="subscription-form" disabled={saving}>
              {saving ? 'Creating…' : 'Create draft'}
            </Button>
          </>
        }
      >
        {form && (
          <form id="subscription-form" onSubmit={save} className="space-y-4">
            <ErrorBox message={formError} />
            <FormGrid>
              <Field label="Customer">
                <Select
                  required
                  value={form.customer}
                  onChange={(event) => setForm({ ...form, customer: event.target.value })}
                >
                  <option value="">Choose a customer…</option>
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Plan">
                <Select
                  required
                  value={form.plan}
                  onChange={(event) => setForm({ ...form, plan: event.target.value })}
                >
                  <option value="">Choose a plan…</option>
                  {planOptions.map((plan) => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name} · {plan.product_name} · {plan.billing_frequency}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Start date">
                <TextInput
                  type="date"
                  required
                  value={form.start_date}
                  onChange={(event) => setForm({ ...form, start_date: event.target.value })}
                />
              </Field>
              <Field label="Expiry date">
                <TextInput
                  type="date"
                  value={form.expiry_date}
                  onChange={(event) => setForm({ ...form, expiry_date: event.target.value })}
                />
              </Field>
              <Field label="Payment terms (days)">
                <TextInput
                  type="number"
                  min="0"
                  value={form.payment_terms_days}
                  onChange={(event) =>
                    setForm({ ...form, payment_terms_days: event.target.value })
                  }
                />
              </Field>
            </FormGrid>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-muted">Lines</span>
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() =>
                    setForm({
                      ...form,
                      lines: [...form.lines, { product: '', quantity: 1, tax_rule: '' }],
                    })
                  }
                >
                  Add line
                </Button>
              </div>
              <div className="space-y-2">
                {form.lines.map((line, index) => (
                  <div key={index} className="grid gap-2 sm:grid-cols-[2fr_80px_1fr_auto]">
                    <Select
                      value={line.product}
                      onChange={(event) => setLine(index, 'product', event.target.value)}
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
                      value={line.quantity}
                      onChange={(event) => setLine(index, 'quantity', event.target.value)}
                    />
                    <Select
                      value={line.tax_rule}
                      onChange={(event) => setLine(index, 'tax_rule', event.target.value)}
                    >
                      <option value="">No tax</option>
                      {taxes.map((tax) => (
                        <option key={tax.id} value={tax.id}>
                          {tax.name} ({Number(tax.rate).toFixed(0)}%)
                        </option>
                      ))}
                    </Select>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setForm({
                          ...form,
                          lines: form.lines.filter((_, i) => i !== index),
                        })
                      }
                      disabled={form.lines.length === 1}
                    >
                      ✕
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
