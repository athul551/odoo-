import { useCallback, useEffect, useState } from 'react'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Checkbox, Field, FormGrid, Select, TextInput } from '../components/ui/Form'
import Modal from '../components/ui/Modal'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { dateOnly, dateTime, titleize } from '../lib/format'

const EMPTY_CREATE = {
  email: '',
  first_name: '',
  last_name: '',
  role: 'staff',
  password: '',
  password_confirm: '',
}

export default function UsersPage() {
  const [rows, setRows] = useState([])
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [createForm, setCreateForm] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/users/', {
        params: { role: role || undefined, q: search || undefined, page_size: 200 },
      })
      setRows(data.results ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [role, search])

  useEffect(() => {
    load()
  }, [load])

  const setCreate = (key) => (event) =>
    setCreateForm((current) => ({ ...current, [key]: event.target.value }))

  const setEdit = (key) => (event) =>
    setEditForm((current) => ({
      ...current,
      [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value,
    }))

  const create = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      await api.post('/users/', {
        email: createForm.email,
        first_name: createForm.first_name || undefined,
        last_name: createForm.last_name || undefined,
        role: createForm.role,
        password: createForm.password,
        password_confirm: createForm.password_confirm,
      })
      setCreateForm(null)
      await load()
    } catch (err) {
      setFormError(apiError(err))
    } finally {
      setSaving(false)
    }
  }

  const saveEdit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      await api.patch(`/users/${editForm.id}/`, {
        first_name: editForm.first_name,
        last_name: editForm.last_name,
        is_active: editForm.is_active,
      })
      setEditForm(null)
      await load()
    } catch (err) {
      setFormError(apiError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-light tracking-tight text-paper">Users</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Staff and admin accounts. Customer accounts are born through public sign-up and are
            read-only here.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Select value={role} onChange={(event) => setRole(event.target.value)} className="w-36">
            <option value="">All roles</option>
            <option value="admin">Admin</option>
            <option value="staff">Staff</option>
            <option value="customer">Customer</option>
          </Select>
          <TextInput
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search email…"
            className="w-52"
          />
          <Button
            onClick={() => {
              setFormError('')
              setCreateForm({ ...EMPTY_CREATE })
            }}
          >
            New staff user
          </Button>
        </div>
      </header>

      <ErrorBox message={error} onRetry={load} />

      <Card bodyClassName="pb-2">
        {loading ? (
          <Loading />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Email</Th>
                <Th>Name</Th>
                <Th>Role</Th>
                <Th>Organization</Th>
                <Th>State</Th>
                <Th>Last login</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && <EmptyRow colSpan={7}>No users match.</EmptyRow>}
              {rows.map((user) => (
                <Tr key={user.id}>
                  <Td className="font-medium text-paper">{user.email}</Td>
                  <Td>
                    {[user.first_name, user.last_name].filter(Boolean).join(' ') || '—'}
                  </Td>
                  <Td>
                    <Badge tone={user.role === 'admin' ? 'accent' : user.role === 'staff' ? 'info' : 'muted'}>
                      {user.role_display ?? titleize(user.role)}
                    </Badge>
                  </Td>
                  <Td>{user.customer?.name ?? '—'}</Td>
                  <Td>
                    <Badge tone={user.is_active ? 'ok' : 'bad'}>
                      {user.is_active ? 'Active' : 'Deactivated'}
                    </Badge>
                  </Td>
                  <Td className="text-xs text-faint">
                    {user.last_login ? dateTime(user.last_login) : 'Never'}
                  </Td>
                  <Td className="text-right">
                    {user.role !== 'customer' && (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => {
                          setFormError('')
                          setEditForm({
                            id: user.id,
                            email: user.email,
                            first_name: user.first_name,
                            last_name: user.last_name,
                            is_active: user.is_active,
                          })
                        }}
                      >
                        Edit
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
        open={createForm !== null}
        title="New staff user"
        subtitle="Staff and admin accounts are provisioned here, never through public sign-up."
        onClose={() => setCreateForm(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateForm(null)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="user-create-form" disabled={saving}>
              {saving ? 'Creating…' : 'Create user'}
            </Button>
          </>
        }
      >
        {createForm && (
          <form id="user-create-form" onSubmit={create} className="space-y-4">
            <ErrorBox message={formError} />
            <FormGrid>
              <Field label="Email" className="sm:col-span-2">
                <TextInput
                  type="email"
                  required
                  value={createForm.email}
                  onChange={setCreate('email')}
                />
              </Field>
              <Field label="First name">
                <TextInput value={createForm.first_name} onChange={setCreate('first_name')} />
              </Field>
              <Field label="Last name">
                <TextInput value={createForm.last_name} onChange={setCreate('last_name')} />
              </Field>
              <Field label="Role">
                <Select value={createForm.role} onChange={setCreate('role')}>
                  <option value="staff">Staff</option>
                  <option value="admin">Admin</option>
                </Select>
              </Field>
              <Field label="Password" hint="At least 9 characters, upper, lower, special.">
                <TextInput
                  type="password"
                  autoComplete="new-password"
                  required
                  value={createForm.password}
                  onChange={setCreate('password')}
                />
              </Field>
              <Field label="Confirm password">
                <TextInput
                  type="password"
                  autoComplete="new-password"
                  required
                  value={createForm.password_confirm}
                  onChange={setCreate('password_confirm')}
                />
              </Field>
            </FormGrid>
          </form>
        )}
      </Modal>

      <Modal
        open={editForm !== null}
        title={editForm ? `Edit ${editForm.email}` : 'Edit user'}
        onClose={() => setEditForm(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditForm(null)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="user-edit-form" disabled={saving}>
              {saving ? 'Saving…' : 'Save user'}
            </Button>
          </>
        }
      >
        {editForm && (
          <form id="user-edit-form" onSubmit={saveEdit} className="space-y-4">
            <ErrorBox message={formError} />
            <FormGrid>
              <Field label="First name">
                <TextInput value={editForm.first_name} onChange={setEdit('first_name')} />
              </Field>
              <Field label="Last name">
                <TextInput value={editForm.last_name} onChange={setEdit('last_name')} />
              </Field>
            </FormGrid>
            <Checkbox
              label="Account is active"
              checked={editForm.is_active}
              onChange={setEdit('is_active')}
            />
            <p className="text-xs text-faint">
              Deactivating blocks sign-in immediately; their historical invoices and payments stay
              attributed to them.
            </p>
          </form>
        )}
      </Modal>
    </div>
  )
}
