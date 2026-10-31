import { useCallback, useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Field, FormGrid, TextInput, Textarea } from '../components/ui/Form'
import Modal, { ConfirmModal } from '../components/ui/Modal'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { dateOnly } from '../lib/format'

const EMPTY = {
  name: '',
  contact_email: '',
  phone: '',
  address_line: '',
  city: '',
  postal_code: '',
  country: '',
  tax_id: '',
  notes: '',
}

export default function CustomersPage() {
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [deleting, setDeleting] = useState(null)

  const pageSize = 20

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/customers/', {
        params: { page, page_size: pageSize, q: search || undefined },
      })
      setRows(data.results ?? [])
      setCount(data.count ?? 0)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [page, search])

  useEffect(() => {
    load()
  }, [load])

  const openCreate = () => {
    setEditing('new')
    setForm(EMPTY)
    setFormError('')
  }

  const openEdit = (customer) => {
    setEditing(customer.id)
    setForm({ ...EMPTY, ...customer })
    setFormError('')
  }

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([key]) => !['id', 'subscription_count', 'created_at', 'updated_at'].includes(key)),
      )
      if (editing === 'new') await api.post('/customers/', payload)
      else await api.patch(`/customers/${editing}/`, payload)
      setEditing(null)
      await load()
    } catch (err) {
      setFormError(apiError(err))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    try {
      await api.delete(`/customers/${deleting.id}/`)
      setDeleting(null)
      await load()
    } catch (err) {
      setError(apiError(err))
      setDeleting(null)
    }
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-paper">Customers</h1>
          <p className="mt-1 text-sm text-faint">Organisations that hold subscriptions.</p>
        </div>
        <div className="flex gap-2">
          <TextInput
            value={search}
            onChange={(event) => {
              setPage(1)
              setSearch(event.target.value)
            }}
            placeholder="Search name or email…"
            className="w-56"
          />
          <Button onClick={openCreate}>New customer</Button>
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
                  <Th>Name</Th>
                  <Th>Contact</Th>
                  <Th>Phone</Th>
                  <Th>Subscriptions</Th>
                  <Th>Created</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && <EmptyRow colSpan={6}>No customers match.</EmptyRow>}
                {rows.map((customer) => (
                  <Tr key={customer.id}>
                    <Td className="font-medium text-paper">{customer.name}</Td>
                    <Td>{customer.contact_email || <span className="text-faint">—</span>}</Td>
                    <Td>{customer.phone || <span className="text-faint">—</span>}</Td>
                    <Td>
                      <Badge>{customer.subscription_count ?? 0}</Badge>
                    </Td>
                    <Td className="text-faint">{dateOnly(customer.created_at)}</Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="xs" variant="ghost" onClick={() => openEdit(customer)}>
                          Edit
                        </Button>
                        <Button size="xs" variant="ghost" onClick={() => setDeleting(customer)}>
                          Delete
                        </Button>
                      </div>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={page}
              pageSize={pageSize}
              count={count}
              onPage={setPage}
              busy={loading}
            />
          </>
        )}
      </Card>

      <Modal
        open={editing !== null}
        title={editing === 'new' ? 'New customer' : 'Edit customer'}
        onClose={() => setEditing(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditing(null)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="customer-form" disabled={saving}>
              {saving ? 'Saving…' : 'Save customer'}
            </Button>
          </>
        }
      >
        <form id="customer-form" onSubmit={save} className="space-y-4">
          <ErrorBox message={formError} />
          <FormGrid>
            <Field label="Name" className="sm:col-span-2">
              <TextInput required value={form.name} onChange={set('name')} />
            </Field>
            <Field label="Contact email">
              <TextInput type="email" value={form.contact_email} onChange={set('contact_email')} />
            </Field>
            <Field label="Phone">
              <TextInput value={form.phone} onChange={set('phone')} />
            </Field>
            <Field label="Address">
              <TextInput value={form.address_line} onChange={set('address_line')} />
            </Field>
            <Field label="City">
              <TextInput value={form.city} onChange={set('city')} />
            </Field>
            <Field label="Postal code">
              <TextInput value={form.postal_code} onChange={set('postal_code')} />
            </Field>
            <Field label="Country">
              <TextInput value={form.country} onChange={set('country')} />
            </Field>
            <Field label="Tax ID" className="sm:col-span-2">
              <TextInput value={form.tax_id} onChange={set('tax_id')} />
            </Field>
            <Field label="Notes" className="sm:col-span-2">
              <Textarea value={form.notes} onChange={set('notes')} />
            </Field>
          </FormGrid>
        </form>
      </Modal>

      <ConfirmModal
        open={deleting !== null}
        title="Delete customer"
        message={`Delete ${deleting?.name ?? 'this customer'}? Customers with subscriptions are protected and will be refused.`}
        confirmLabel="Delete"
        onConfirm={remove}
        onClose={() => setDeleting(null)}
      />
    </div>
  )
}
