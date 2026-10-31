import { useCallback, useEffect, useState } from 'react'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import Card from '../ui/Card'
import { ErrorBox, Loading } from '../ui/Feedback'
import { Field, FormGrid, Select, TextInput, Textarea } from '../ui/Form'
import Modal from '../ui/Modal'
import { EmptyRow, Table, Td, Th, Tr } from '../ui/Table'
import api, { apiError } from '../../lib/api'
import { dateOnly } from '../../lib/format'

const EMPTY = {
  name: '',
  plan: '',
  validity_days: 30,
  payment_terms_days: 30,
  notes: '',
  active: true,
}

export default function QuotationTemplates() {
  const [rows, setRows] = useState([])
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [templates, planList] = await Promise.all([
        api.get('/quotation-templates/', { params: { page_size: 200 } }),
        api.get('/plans/', { params: { page_size: 200, include_archived: true } }),
      ])
      setRows(templates.data.results ?? [])
      setPlans(planList.data.results ?? [])
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
              setForm({ ...EMPTY, plan: plans[0]?.id ?? '' })
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
          </form>
        )}
      </Modal>
    </>
  )
}
