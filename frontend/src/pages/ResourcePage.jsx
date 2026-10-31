import { useEffect, useMemo, useState } from 'react'
import api from '../lib/api'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'

const configs = {
  customers: {
    title: 'Customers', description: 'Manage your customer relationships and account details.', endpoint: '/customers/',
    action: 'Add customer', columns: ['Customer', 'Contact', 'Subscriptions', 'Status', 'Last activity'],
    rows: [['Acme Corporation', 'hello@acme.co', '12', 'Active', 'Today'], ['Northstar Labs', 'finance@northstar.io', '8', 'Active', 'Yesterday'], ['Vantage Systems', 'billing@vantage.com', '5', 'Active', 'Oct 28, 2026'], ['Solstice Studio', 'team@solstice.studio', '2', 'At risk', 'Oct 24, 2026']],
  },
  products: {
    title: 'Products', description: 'Manage the products and services you offer to customers.', endpoint: '/products/',
    action: 'Add product', columns: ['Product', 'Type', 'Sales price', 'Variants', 'Status'],
    rows: [['Growth Suite', 'Service', '$249.00', '3 variants', 'Active'], ['Analytics Pro', 'Service', '$499.00', '2 variants', 'Active'], ['Priority Support', 'Add-on', '$99.00', '—', 'Active'], ['Legacy Reports', 'Service', '$149.00', '—', 'Archived']],
  },
  plans: {
    title: 'Plans', description: 'Configure recurring billing plans and lifecycle rules.', endpoint: '/plans/',
    action: 'Create plan', columns: ['Plan', 'Product', 'Billing frequency', 'Price', 'Status'],
    rows: [['Growth Monthly', 'Growth Suite', 'Monthly', '$249.00', 'Active'], ['Growth Annual', 'Growth Suite', 'Yearly', '$2,390.00', 'Active'], ['Analytics Monthly', 'Analytics Pro', 'Monthly', '$499.00', 'Active'], ['Legacy Annual', 'Legacy Reports', 'Yearly', '$1,490.00', 'Archived']],
  },
  quotations: {
    title: 'Quotations', description: 'Create, send, and track customer quotations.', endpoint: '/quotation-templates/',
    action: 'New quotation', columns: ['Quotation', 'Customer', 'Amount', 'Valid until', 'Status'],
    rows: [['QT-2026-0148', 'Acme Corporation', '$2,490.00', 'Nov 14, 2026', 'Sent'], ['QT-2026-0147', 'Northstar Labs', '$8,400.00', 'Nov 08, 2026', 'Draft'], ['QT-2026-0142', 'Vantage Systems', '$1,980.00', 'Oct 31, 2026', 'Accepted'], ['QT-2026-0138', 'Solstice Studio', '$890.00', 'Oct 22, 2026', 'Expired']],
  },
  subscriptions: {
    title: 'Subscriptions', description: 'Track subscription lifecycles, renewals, and customer plans.', endpoint: '/subscriptions/',
    action: 'New subscription', columns: ['Subscription', 'Customer', 'Plan', 'Renewal date', 'Status'],
    rows: [['SUB-2026-000128', 'Acme Corporation', 'Growth Annual', 'Jan 18, 2027', 'Active'], ['SUB-2026-000127', 'Northstar Labs', 'Analytics Monthly', 'Nov 05, 2026', 'Active'], ['SUB-2026-000126', 'Vantage Systems', 'Growth Monthly', 'Nov 02, 2026', 'Paused'], ['SUB-2026-000119', 'Solstice Studio', 'Growth Monthly', '—', 'Closed']],
  },
  invoices: {
    title: 'Invoices', description: 'Review recurring invoices, payment status, and collections.', endpoint: '/invoices/',
    action: 'Create invoice', columns: ['Invoice', 'Customer', 'Due date', 'Amount', 'Status'],
    rows: [['INV-2026-0842', 'Acme Corporation', 'Nov 27, 2026', '$2,400.00', 'Paid'], ['INV-2026-0837', 'Northstar Labs', 'Nov 26, 2026', '$1,850.00', 'Paid'], ['INV-2026-0831', 'Vantage Systems', 'Oct 26, 2026', '$4,200.00', 'Overdue'], ['INV-2026-0824', 'Solstice Studio', 'Nov 23, 2026', '$980.00', 'Outstanding']],
  },
  payments: {
    title: 'Payments', description: 'Monitor incoming payments and keep your ledger accurate.', endpoint: '/payments/',
    action: 'Record payment', columns: ['Reference', 'Customer', 'Invoice', 'Payment date', 'Amount'],
    rows: [['PAY-2026-0901', 'Acme Corporation', 'INV-2026-0842', 'Oct 28, 2026', '$2,400.00'], ['PAY-2026-0898', 'Northstar Labs', 'INV-2026-0837', 'Oct 27, 2026', '$1,850.00'], ['PAY-2026-0891', 'Solstice Studio', 'INV-2026-0824', 'Oct 24, 2026', '$980.00'], ['PAY-2026-0884', 'Vantage Systems', 'INV-2026-0806', 'Oct 18, 2026', '$3,200.00']],
  },
  discounts: {
    title: 'Discounts', description: 'Create and manage promotional pricing rules.', endpoint: '/discount-rules/',
    action: 'Create discount', columns: ['Discount rule', 'Type', 'Value', 'Usage', 'Status'],
    rows: [['Launch 10', 'Percentage', '10%', '42 / 100', 'Active'], ['Annual upgrade', 'Fixed amount', '$250.00', '18 / 50', 'Active'], ['Partner credit', 'Percentage', '15%', '100 / 100', 'Exhausted'], ['Summer offer', 'Percentage', '20%', '—', 'Inactive']],
  },
}

function normalizeRows(data, config) {
  if (!Array.isArray(data)) return config.rows
  return data.map((item) => config.columns.map((column, index) => {
    const key = column.toLowerCase().replaceAll(' ', '_')
    return item[key] ?? item.name ?? item.number ?? item.id ?? '—'
  }))
}

function statusClass(value) {
  const status = String(value).toLowerCase()
  if (status.includes('active') || status.includes('paid') || status.includes('accepted')) return 'active'
  if (status.includes('overdue') || status.includes('expired') || status.includes('closed') || status.includes('inactive')) return 'danger'
  if (status.includes('paused') || status.includes('pending') || status.includes('draft') || status.includes('outstanding') || status.includes('at risk')) return 'warning'
  return ''
}

export default function ResourcePage({ resource }) {
  const config = configs[resource]
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState(config.rows)
  const [loading, setLoading] = useState(false)
  const [sortAscending, setSortAscending] = useState(true)
  const [filterOpen, setFilterOpen] = useState(false)
  const [modal, setModal] = useState(null)

  useEffect(() => {
    let mounted = true
    setLoading(true)
    api.get(config.endpoint).then(({ data }) => {
      if (mounted) setRows(normalizeRows(data.results, config))
    }).catch(() => {}).finally(() => mounted && setLoading(false))
    return () => { mounted = false }
  }, [config.endpoint])

  const visibleRows = useMemo(() => rows
    .filter((row) => row.join(' ').toLowerCase().includes(query.toLowerCase()))
    .sort((left, right) => sortAscending ? left[0].localeCompare(right[0]) : right[0].localeCompare(left[0])), [rows, query, sortAscending])

  return <div className="resource-page">
    <div className="page-heading resource-heading">
      <div><p className="eyebrow">Workspace / {config.title}</p><h1>{config.title}</h1><p className="heading-subtitle">{config.description}</p></div>
      <Button onClick={() => setModal({ title: config.action })}>＋ {config.action}</Button>
    </div>
    <Card className="resource-card">
      <div className="resource-toolbar">
        <label className="resource-search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${config.title.toLowerCase()}...`} /></label>
        <div className="toolbar-actions"><button className={`filter-button ${filterOpen ? 'selected-filter' : ''}`} onClick={() => setFilterOpen((value) => !value)}>≡ Filters</button><button className="filter-button" onClick={() => setSortAscending((value) => !value)}>↕ {sortAscending ? 'A–Z' : 'Z–A'}</button><button className="filter-button" onClick={() => setQuery('')}>Clear</button></div>
      </div>
      {filterOpen && <div className="filter-panel"><span>Quick filters</span><button onClick={() => setQuery('Active')}>Active</button><button onClick={() => setQuery('Draft')}>Draft</button><button onClick={() => setQuery('')}>All records</button></div>}
      <div className="resource-summary"><span><strong>{visibleRows.length}</strong> records</span><span className="table-view-toggle">▦ Table &nbsp; ◫ Board</span></div>
      <div className="table-wrap resource-table"><table><thead><tr>{config.columns.map((column) => <th key={column}>{column}</th>)}<th aria-label="Actions" /></tr></thead><tbody>
        {loading && <tr><td colSpan={config.columns.length + 1} className="empty-row">Loading records...</td></tr>}
        {!loading && visibleRows.map((row, rowIndex) => <tr key={`${row[0]}-${rowIndex}`}>{row.map((cell, index) => <td key={`${cell}-${index}`} className={index === 0 ? 'primary-cell' : ''}>{config.columns[index]?.toLowerCase().includes('status') ? <span className={`status-badge ${statusClass(cell)}`}>{cell}</span> : cell}</td>)}<td><button className="row-action" onClick={() => setModal({ title: row[0], detail: row })} aria-label={`Open ${row[0]}`}>•••</button></td></tr>)}
        {!loading && visibleRows.length === 0 && <tr><td colSpan={config.columns.length + 1} className="empty-row">No records match your search.</td></tr>}
      </tbody></table></div>
      <div className="resource-pagination"><span>Showing 1–{visibleRows.length} of {rows.length}</span><div><button disabled>←</button><button className="current-page">1</button><button disabled>→</button></div></div>
    </Card>
    {modal && <Modal title={modal.title} onClose={() => setModal(null)}>
      {modal.detail ? <div className="record-detail">{config.columns.map((column, index) => <div key={column}><span>{column}</span><strong>{modal.detail[index]}</strong></div>)}</div> : <form onSubmit={(event) => { event.preventDefault(); setModal(null) }}><p className="modal-description">This form is ready to connect to the {config.title.toLowerCase()} API.</p><label className="modal-field">Name<input required autoFocus placeholder={`Enter ${config.title.toLowerCase()} name`} /></label><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setModal(null)}>Cancel</button><button className="primary-button">Save draft</button></div></form>}
    </Modal>}
  </div>
}

export { configs }
