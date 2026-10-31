import { useCallback, useEffect, useState } from 'react'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Checkbox, Field, FormGrid, Select, TextInput } from '../components/ui/Form'
import Modal, { ConfirmModal } from '../components/ui/Modal'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { dateOnly, money, titleize, todayISO } from '../lib/format'

const EMPTY = {
  name: '',
  scope: 'product',
  kind: 'percent',
  value: '',
  applies_from: '',
  applies_until: '',
  minimum_amount: '',
  minimum_quantity: '',
  usage_limit: '',
  active: true,
}

export default function DiscountsPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [deactivating, setDeactivating] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/discount-rules/', { params: { page_size: 200 } })
      setRows(data.results ?? [])
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

  const openCreate = () => {
    setForm({ ...EMPTY, applies_from: todayISO() })
    setFormError('')
  }

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const payload = {
        name: form.name,
        scope: form.scope,
        kind: form.kind,
        value: form.value,
        applies_from: form.applies_from,
        applies_until: form.applies_until || undefined,
        minimum_amount: form.minimum_amount || undefined,
        minimum_quantity: form.minimum_quantity || undefined,
        usage_limit: form.usage_limit || undefined,
        active: form.active,
      }
      await api.post('/discount-rules/', payload)
      setForm(null)
      await load()
    } catch (err) {
      setFormError(apiError(err))
    } finally {
      setSaving(false)
    }
  }

  const deactivate = async () => {
    setSaving(true)
    setError('')
    try {
      await api.post(`/discount-rules/${deactivating.id}/deactivate/`)
      setDeactivating(null)
      await load()
    } catch (err) {
      setError(apiError(err))
      setDeactivating(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-light tracking-tight text-paper">Discounts</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Rules are never deleted: deactivating keeps every issued invoice truthful.
          </p>
        </div>
        <Button onClick={openCreate}>New rule</Button>
      </header>

      <ErrorBox message={error} onRetry={load} />

      <Card bodyClassName="pb-2">
        {loading ? (
          <Loading />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Scope</Th>
                <Th>Kind</Th>
                <Th className="text-right">Value</Th>
                <Th>Window</Th>
                <Th>Minimums</Th>
                <Th>Usage</Th>
                <Th>State</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <EmptyRow colSpan={9}>No discount rules yet.</EmptyRow>
              )}
              {rows.map((rule) => (
                <Tr key={rule.id}>
                  <Td className="font-medium text-paper">{rule.name}</Td>
                  <Td>{titleize(rule.scope)}</Td>
                  <Td>{titleize(rule.kind)}</Td>
                  <Td className="text-right">
                    {rule.kind === 'percent' ? `${money(rule.value)}%` : money(rule.value)}
                  </Td>
                  <Td className="whitespace-nowrap text-xs">
                    {dateOnly(rule.applies_from)} →{' '}
                    {rule.applies_until ? dateOnly(rule.applies_until) : 'open'}
                  </Td>
                  <Td className="text-xs">
                    {rule.minimum_amount ? `≥ ${money(rule.minimum_amount)}` : '—'}
                    {rule.minimum_quantity ? ` · qty ≥ ${rule.minimum_quantity}` : ''}
                  </Td>
                  <Td>
                    <Badge>
                      {rule.usage_count}
                      {rule.usage_limit ? ` / ${rule.usage_limit}` : ''}
                    </Badge>
                  </Td>
                  <Td>
                    <Badge tone={rule.active ? 'ok' : 'muted'}>
                      {rule.active ? 'Active' : 'Inactive'}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    {rule.active && (
                      <Button size="xs" variant="ghost" onClick={() => setDeactivating(rule)}>
                        Deactivate
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Modal
        open={form !== null}
        title="New discount rule"
        subtitle="Percent or fixed amount, scoped to products or whole subscriptions."
        onClose={() => setForm(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setForm(null)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="discount-form" disabled={saving}>
              {saving ? 'Saving…' : 'Create rule'}
            </Button>
          </>
        }
      >
        {form && (
          <form id="discount-form" onSubmit={save} className="space-y-4">
            <ErrorBox message={formError} />
            <FormGrid>
              <Field label="Name" className="sm:col-span-2">
                <TextInput required value={form.name} onChange={set('name')} />
              </Field>
              <Field label="Scope">
                <Select value={form.scope} onChange={set('scope')}>
                  <option value="product">Specific products</option>
                  <option value="subscription">Whole subscriptions</option>
                </Select>
              </Field>
              <Field label="Kind">
                <Select value={form.kind} onChange={set('kind')}>
                  <option value="percent">Percentage</option>
                  <option value="amount">Fixed amount</option>
                </Select>
              </Field>
              <Field label={form.kind === 'percent' ? 'Value (%)' : 'Value'}>
                <TextInput
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={form.value}
                  onChange={set('value')}
                />
              </Field>
              <Field label="Usage limit" hint="Empty = unlimited">
                <TextInput
                  type="number"
                  min="1"
                  value={form.usage_limit}
                  onChange={set('usage_limit')}
                />
              </Field>
              <Field label="Applies from">
                <TextInput
                  type="date"
                  required
                  value={form.applies_from}
                  onChange={set('applies_from')}
                />
              </Field>
              <Field label="Applies until" hint="Empty = open-ended">
                <TextInput
                  type="date"
                  value={form.applies_until}
                  onChange={set('applies_until')}
                />
              </Field>
              <Field label="Minimum amount" hint="Optional">
                <TextInput
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.minimum_amount}
                  onChange={set('minimum_amount')}
                />
              </Field>
              <Field label="Minimum quantity" hint="Optional">
                <TextInput
                  type="number"
                  min="1"
                  value={form.minimum_quantity}
                  onChange={set('minimum_quantity')}
                />
              </Field>
              <div className="sm:col-span-2">
                <Checkbox
                  label="Active immediately"
                  checked={form.active}
                  onChange={set('active')}
                />
              </div>
            </FormGrid>
          </form>
        )}
      </Modal>

      <ConfirmModal
        open={deactivating !== null}
        title="Deactivate discount rule"
        message={`Deactivate “${deactivating?.name ?? ''}”? Issued invoices keep their discount; new billing runs stop applying it.`}
        confirmLabel="Deactivate"
        onConfirm={deactivate}
        onClose={() => setDeactivating(null)}
        busy={saving}
      />
    </div>
  )
}
