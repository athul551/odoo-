import { useCallback, useEffect, useState } from 'react'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import Card from '../ui/Card'
import { ErrorBox, Loading } from '../ui/Feedback'
import { Field, FormGrid, Select, TextInput, Textarea } from '../ui/Form'
import Modal from '../ui/Modal'
import { EmptyRow, Table, Td, Th, Tr } from '../ui/Table'
import api, { apiError } from '../../lib/api'
import { dateOnly, money } from '../../lib/format'

const EMPTY = {
  name: '',
  plan: '',
  validity_days: 30,
  payment_terms_days: 30,
  notes: '',
  active: true,
  lines: [],
}

export default function QuotationTemplates() {
  const [rows, setRows] = useState([])
  const [plans, setPlans] = useState([])
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [templates, planList, productList] = await Promise.all([
        api.get('/quotation-templates/', { params: { page_size: 200 } }),
        api.get('/plans/', { params: { page_size: 200, include_archived: true } }),
        api.get('/products/', { params: { page_size: 200 } }),
      ])
      setRows(templates.data.results ?? [])
      setPlans(planList.data.results ?? [])
      setProducts(productList.data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const set = (key) => (event) =>
    setForm((current) => ({
      ...current,
      [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value,
    }))

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      await api.post('/quotation-templates/', {
        name: form.name,
        plan: Number(form.plan),
        validity_days: Number(form.validity_days),
        payment_terms_days: Number(form.payment_terms_days),
        notes: form.notes,
        active: form.active,
        lines: form.lines.map((line) => ({
          product: Number(line.product),
          variant: line.variant ? Number(line.variant) : undefined,
          quantity: Number(line.quantity),
        })),
      })
      setForm(null)
      await load()
    } catch (err) {
      setFormError(apiError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Card
        title="Quotation templates"
        subtitle="The blueprint a quotation starts from; lines are snapshotted when used."
        actions={
          <Button
            size="sm"
            onClick={() => {
              setFormError('')
              setForm({ ...EMPTY, plan: plans[0]?.id ?? '', lines: [] })
            }}
          >
            New template
          </Button>
        }
        bodyClassName="pb-2"
      >
        <ErrorBox message={error} onRetry={load} />
        {loading ? (
          <Loading />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Plan</Th>
                <Th>Validity</Th>
                <Th>Payment terms</Th>
                <Th>Lines</Th>
                <Th>State</Th>
                <Th>Created</Th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && <EmptyRow colSpan={7}>No templates yet.</EmptyRow>}
              {rows.map((template) => (
                <Tr key={template.id}>
                  <Td className="font-medium text-paper">{template.name}</Td>
                  <Td>{template.plan_name}</Td>
                  <Td>{template.validity_days} days</Td>
                  <Td>{template.payment_terms_days} days</Td>
                  <Td>
                    <Badge>{template.lines?.length ?? 0}</Badge>
                  </Td>
                  <Td>
                    <Badge tone={template.active ? 'ok' : 'muted'}>
                      {template.active ? 'Active' : 'Archived'}
                    </Badge>
                  </Td>
                  <Td className="text-xs text-faint">{dateOnly(template.created_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Modal
        open={form !== null}
        title="New quotation template"
        onClose={() => setForm(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setForm(null)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="template-form" disabled={saving}>
              {saving ? 'Saving…' : 'Create template'}
            </Button>
          </>
        }
      >
        {form && (
          <form id="template-form" onSubmit={save} className="space-y-4">
            <ErrorBox message={formError} />
            <FormGrid>
              <Field label="Name" className="sm:col-span-2">
                <TextInput required value={form.name} onChange={set('name')} />
              </Field>
              <Field label="Plan">
                <Select required value={form.plan} onChange={set('plan')}>
                  <option value="">Choose a plan…</option>
                  {plans.map((plan) => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name} · {plan.product_name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Validity (days)">
                <TextInput
                  type="number"
                  min="1"
                  value={form.validity_days}
                  onChange={set('validity_days')}
                />
              </Field>
              <Field label="Payment terms (days)">
                <TextInput
                  type="number"
                  min="0"
                  value={form.payment_terms_days}
                  onChange={set('payment_terms_days')}
                />
              </Field>
              <Field label="Notes" className="sm:col-span-2">
                <Textarea value={form.notes} onChange={set('notes')} />
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
                      lines: [
                        ...form.lines,
                        { product: '', variant: '', quantity: 1 },
                      ],
                    })
                  }
                >
                  Add line
                </Button>
              </div>
              <div className="space-y-2">
                {form.lines.length === 0 && (
                  <p className="text-xs text-faint">
                    No lines yet — a template without lines is just a plan shortcut.
                  </p>
                )}
                {form.lines.map((line, index) => {
                  const product = products.find(
                    (row) => String(row.id) === String(line.product),
                  )
                  const variants = product?.variants ?? []
                  return (
                    <div
                      key={index}
                      className="grid gap-2 sm:grid-cols-[2fr_1.2fr_70px_auto]"
                    >
                      <Select
                        required
                        value={line.product}
                        onChange={(event) => {
                          const lines = form.lines.map((row, i) =>
                            i === index
                              ? { ...row, product: event.target.value, variant: '' }
                              : row,
                          )
                          setForm({ ...form, lines })
                        }}
                      >
                        <option value="">Product…</option>
                        {products.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name} · {money(row.sales_price)}
                          </option>
                        ))}
                      </Select>
                      <Select
                        value={line.variant}
                        disabled={variants.length === 0}
                        onChange={(event) => {
                          const lines = form.lines.map((row, i) =>
                            i === index ? { ...row, variant: event.target.value } : row,
                          )
                          setForm({ ...form, lines })
                        }}
                      >
                        <option value="">{variants.length ? 'No variant' : 'No variants'}</option>
                        {variants.map((variant) => (
                          <option key={variant.id} value={variant.id}>
                            {variant.attribute}: {variant.value} (+{money(variant.price_delta)})
                          </option>
                        ))}
                      </Select>
                      <TextInput
                        type="number"
                        min="1"
                        value={line.quantity}
                        onChange={(event) => {
                          const lines = form.lines.map((row, i) =>
                            i === index ? { ...row, quantity: event.target.value } : row,
                          )
                          setForm({ ...form, lines })
                        }}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setForm({
                            ...form,
                            lines: form.lines.filter((_, i) => i !== index),
                          })
                        }
                      >
                        ✕
                      </Button>
                    </div>
                  )
                })}
              </div>
            </div>
          </form>
        )}
      </Modal>
    </>
  )
}
