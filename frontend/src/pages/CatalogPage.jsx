import { useCallback, useEffect, useState } from 'react'
import Pagination from '../components/Pagination'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { ErrorBox, Loading } from '../components/ui/Feedback'
import { Checkbox, Field, FormGrid, Select, TextInput, Textarea } from '../components/ui/Form'
import Modal from '../components/ui/Modal'
import Tabs from '../components/ui/Tabs'
import QuotationTemplates from '../components/catalog/QuotationTemplates'
import { EmptyRow, Table, Td, Th, Tr } from '../components/ui/Table'
import api, { apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateOnly, money, titleize } from '../lib/format'

const FREQUENCIES = ['daily', 'weekly', 'monthly', 'yearly']
const PRODUCT_TYPES = ['service', 'goods', 'addon']

const emptyProduct = {
  name: '',
  type: 'service',
  sales_price: '0.00',
  cost_price: '0.00',
  notes: '',
  active: true,
}

const emptyPlan = {
  product: '',
  name: '',
  billing_frequency: 'monthly',
  price: '0.00',
  minimum_quantity: 1,
  availability_start: '',
  availability_end: '',
  auto_close_on_expiry: false,
  allow_early_close: true,
  allow_pause: true,
  allow_renew: true,
  active: true,
  notes: '',
}

export default function CatalogPage() {
  const { isAdmin } = useAuth()
  const [tab, setTab] = useState('products')
  const [error, setError] = useState('')

  const [products, setProducts] = useState([])
  const [plans, setPlans] = useState([])
  const [taxes, setTaxes] = useState([])
  const [loading, setLoading] = useState(true)

  const [productForm, setProductForm] = useState(null)
  const [planForm, setPlanForm] = useState(null)
  const [taxForm, setTaxForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [productRes, planRes, taxRes] = await Promise.all([
        api.get('/products/', { params: { page_size: 200 } }),
        api.get('/plans/', { params: { page_size: 200, include_archived: true } }),
        api.get('/tax-rules/', { params: { page_size: 200 } }),
      ])
      setProducts(productRes.data.results ?? productRes.data ?? [])
      setPlans(planRes.data.results ?? planRes.data ?? [])
      setTaxes(taxRes.data.results ?? taxRes.data ?? [])
    } catch (err) {
      setError(apiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const submit = async (event, endpoint, form, setter, collection) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const payload = { ...form }
      delete payload.id
      delete payload.product_name
      delete payload.is_selectable
      delete payload.created_at
      delete payload.updated_at
      if (endpoint === 'plans') {
        if (!payload.availability_end) delete payload.availability_end
      }
      if (endpoint === 'products') {
        delete payload.variants
      }
      if (form.id) await api.patch(`/${endpoint}/${form.id}/`, payload)
      else await api.post(`/${endpoint}/`, payload)
      setter(null)
      await load()
    } catch (err) {
      setFormError(apiError(err))
    } finally {
      setSaving(false)
    }
  }

  const setterFor = (key) => (event) => {
    const target = key === 'product' ? productForm : key === 'plan' ? planForm : taxForm
    const set = key === 'product' ? setProductForm : key === 'plan' ? setPlanForm : setTaxForm
    const name = event.target.name
    const value =
      event.target.type === 'checkbox' ? event.target.checked : event.target.value
    set({ ...target, [name]: value })
  }

  const modal = () => {
    if (productForm) {
      return (
        <Modal
          open
          title={productForm.id ? 'Edit product' : 'New product'}
          onClose={() => setProductForm(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setProductForm(null)} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" form="product-form" disabled={saving}>
                {saving ? 'Saving…' : 'Save product'}
              </Button>
            </>
          }
        >
          <form
            id="product-form"
            onSubmit={(event) => submit(event, 'products', productForm, setProductForm)}
            className="space-y-4"
          >
            <ErrorBox message={formError} />
            <FormGrid>
              <Field label="Name" className="sm:col-span-2">
                <TextInput name="name" required value={productForm.name} onChange={setterFor('product')} />
              </Field>
              <Field label="Type">
                <Select name="type" value={productForm.type} onChange={setterFor('product')}>
                  {PRODUCT_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {titleize(type)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Sales price">
                <TextInput
                  name="sales_price"
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={productForm.sales_price}
                  onChange={setterFor('product')}
                />
              </Field>
              <Field label="Cost price">
                <TextInput
                  name="cost_price"
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={productForm.cost_price}
                  onChange={setterFor('product')}
                />
              </Field>
              <Field label="Active">
                <Checkbox
                  name="active"
                  label="Selectable in new subscriptions"
                  checked={productForm.active}
                  onChange={setterFor('product')}
                />
              </Field>
              <Field label="Notes" className="sm:col-span-2">
                <Textarea name="notes" value={productForm.notes} onChange={setterFor('product')} />
              </Field>
            </FormGrid>
          </form>
        </Modal>
      )
    }

    if (planForm) {
      return (
        <Modal
          open
          wide
          title={planForm.id ? 'Edit plan' : 'New plan'}
          onClose={() => setPlanForm(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setPlanForm(null)} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" form="plan-form" disabled={saving}>
                {saving ? 'Saving…' : 'Save plan'}
              </Button>
            </>
          }
        >
          <form
            id="plan-form"
            onSubmit={(event) => submit(event, 'plans', planForm, setPlanForm)}
            className="space-y-4"
          >
            <ErrorBox message={formError} />
            <FormGrid>
              <Field label="Product">
                <Select name="product" required value={planForm.product} onChange={setterFor('plan')}>
                  <option value="">Choose a product…</option>
                  {products.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Name">
                <TextInput name="name" required value={planForm.name} onChange={setterFor('plan')} />
              </Field>
              <Field label="Billing frequency">
                <Select
                  name="billing_frequency"
                  value={planForm.billing_frequency}
                  onChange={setterFor('plan')}
                >
                  {FREQUENCIES.map((frequency) => (
                    <option key={frequency} value={frequency}>
                      {titleize(frequency)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Price">
                <TextInput
                  name="price"
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={planForm.price}
                  onChange={setterFor('plan')}
                />
              </Field>
              <Field label="Minimum quantity">
                <TextInput
                  name="minimum_quantity"
                  type="number"
                  min="1"
                  value={planForm.minimum_quantity}
                  onChange={setterFor('plan')}
                />
              </Field>
              <Field label="Availability start">
                <TextInput
                  name="availability_start"
                  type="date"
                  required
                  value={planForm.availability_start}
                  onChange={setterFor('plan')}
                />
              </Field>
              <Field label="Availability end" hint="Empty = open-ended">
                <TextInput
                  name="availability_end"
                  type="date"
                  value={planForm.availability_end ?? ''}
                  onChange={setterFor('plan')}
                />
              </Field>
              <Field label="Behaviors" className="sm:col-span-2">
                <div className="grid gap-2 sm:grid-cols-2">
                  <Checkbox
                    name="auto_close_on_expiry"
                    label="Auto-close at expiry"
                    checked={planForm.auto_close_on_expiry}
                    onChange={setterFor('plan')}
                  />
                  <Checkbox
                    name="allow_early_close"
                    label="Allow early close"
                    checked={planForm.allow_early_close}
                    onChange={setterFor('plan')}
                  />
                  <Checkbox
                    name="allow_pause"
                    label="Allow pause"
                    checked={planForm.allow_pause}
                    onChange={setterFor('plan')}
                  />
                  <Checkbox
                    name="allow_renew"
                    label="Allow renew"
                    checked={planForm.allow_renew}
                    onChange={setterFor('plan')}
                  />
                </div>
              </Field>
              <Field label="Notes" className="sm:col-span-2">
                <Textarea name="notes" value={planForm.notes} onChange={setterFor('plan')} />
              </Field>
            </FormGrid>
          </form>
        </Modal>
      )
    }

    if (taxForm) {
      return (
        <Modal
          open
          title={taxForm.id ? 'Edit tax rule' : 'New tax rule'}
          onClose={() => setTaxForm(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setTaxForm(null)} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" form="tax-form" disabled={saving}>
                {saving ? 'Saving…' : 'Save tax rule'}
              </Button>
            </>
          }
        >
          <form
            id="tax-form"
            onSubmit={(event) => submit(event, 'tax-rules', taxForm, setTaxForm)}
            className="space-y-4"
          >
            <ErrorBox message={formError} />
            <Field label="Name">
              <TextInput name="name" required value={taxForm.name} onChange={setterFor('tax')} />
            </Field>
            <Field label="Rate (%)">
              <TextInput
                name="rate"
                type="number"
                step="0.01"
                min="0"
                max="100"
                required
                value={taxForm.rate}
                onChange={setterFor('tax')}
              />
            </Field>
            <Checkbox
              name="active"
              label="Active"
              checked={taxForm.active}
              onChange={setterFor('tax')}
            />
          </form>
        </Modal>
      )
    }

    return null
  }

  const canWrite = isAdmin

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-paper">Catalog</h1>
        <p className="mt-1 text-sm text-faint">
          Products, plans and tax rules. Only admins may change the catalog.
        </p>
      </header>

      <ErrorBox message={error} onRetry={load} />

      <Tabs
        tabs={[
          { id: 'products', label: 'Products', count: products.length },
          { id: 'plans', label: 'Plans', count: plans.length },
          { id: 'taxes', label: 'Tax rules', count: taxes.length },
          { id: 'templates', label: 'Templates' },
        ]}
        active={tab}
        onChange={setTab}
      />

      {loading ? (
        <Loading />
      ) : tab === 'products' ? (
        <Card
          title="Products"
          actions={
            canWrite && (
              <Button size="sm" onClick={() => { setFormError(''); setProductForm({ ...emptyProduct }) }}>
                New product
              </Button>
            )
          }
        >
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Type</Th>
                <Th>Sales price</Th>
                <Th>Cost</Th>
                <Th>Variants</Th>
                <Th>Active</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {products.length === 0 && <EmptyRow colSpan={7}>No products yet.</EmptyRow>}
              {products.map((product) => (
                <Tr key={product.id}>
                  <Td className="font-medium text-paper">{product.name}</Td>
                  <Td>{titleize(product.type)}</Td>
                  <Td>{money(product.sales_price)}</Td>
                  <Td>{money(product.cost_price)}</Td>
                  <Td>
                    <Badge>{product.variants?.length ?? 0}</Badge>
                  </Td>
                  <Td>
                    <Badge tone={product.active ? 'emerald' : 'slate'}>
                      {product.active ? 'Active' : 'Archived'}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    {canWrite && (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => { setFormError(''); setProductForm({ ...product }) }}
                      >
                        Edit
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : tab === 'plans' ? (
        <Card
          title="Plans"
          actions={
            canWrite && (
              <Button
                size="sm"
                onClick={() => {
                  setFormError('')
                  setPlanForm({
                    ...emptyPlan,
                    availability_start: new Date().toISOString().slice(0, 10),
                    product: products[0]?.id ?? '',
                  })
                }}
              >
                New plan
              </Button>
            )
          }
        >
          <Table>
            <thead>
              <tr>
                <Th>Plan</Th>
                <Th>Product</Th>
                <Th>Frequency</Th>
                <Th>Price</Th>
                <Th>Behaviors</Th>
                <Th>Availability</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {plans.length === 0 && <EmptyRow colSpan={7}>No plans yet.</EmptyRow>}
              {plans.map((plan) => (
                <Tr key={plan.id}>
                  <Td className="font-medium text-paper">{plan.name}</Td>
                  <Td>{plan.product_name}</Td>
                  <Td>{titleize(plan.billing_frequency)}</Td>
                  <Td>{money(plan.price)}</Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {plan.auto_close_on_expiry && <Badge tone="amber">Auto-close</Badge>}
                      {plan.allow_pause && <Badge>Pause</Badge>}
                      {plan.allow_renew && <Badge>Renew</Badge>}
                      {plan.allow_early_close && <Badge>Early close</Badge>}
                    </div>
                  </Td>
                  <Td className="text-faint">
                    {dateOnly(plan.availability_start)} →{' '}
                    {plan.availability_end ? dateOnly(plan.availability_end) : 'open'}
                  </Td>
                  <Td className="text-right">
                    {canWrite && (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => { setFormError(''); setPlanForm({ ...plan }) }}
                      >
                        Edit
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : tab === 'templates' ? (
        <QuotationTemplates />
      ) : (
        <Card
          title="Tax rules"
          actions={
            canWrite && (
              <Button
                size="sm"
                onClick={() => { setFormError(''); setTaxForm({ name: '', rate: '0.00', active: true }) }}
              >
                New tax rule
              </Button>
            )
          }
        >
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Rate</Th>
                <Th>Active</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {taxes.length === 0 && <EmptyRow colSpan={4}>No tax rules yet.</EmptyRow>}
              {taxes.map((tax) => (
                <Tr key={tax.id}>
                  <Td className="font-medium text-paper">{tax.name}</Td>
                  <Td>{Number(tax.rate).toFixed(2)}%</Td>
                  <Td>
                    <Badge tone={tax.active ? 'emerald' : 'slate'}>
                      {tax.active ? 'Active' : 'Inactive'}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    {canWrite && (
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => { setFormError(''); setTaxForm({ ...tax }) }}
                      >
                        Edit
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}

      {modal()}
    </div>
  )
}
